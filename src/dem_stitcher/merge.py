import concurrent.futures
import math
import warnings

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import MERGE_METHODS, merge
from rasterio.windows import Window
from shapely.geometry import box
from tqdm import tqdm

from .rio_tools import in_memory_profile
from .rio_window import format_window_profile, get_window_from_extent


def merge_tile_datasets_within_extent(
    datasets: list[rasterio.DatasetReader] | list[str],
    extent: list,
    resampling: str = 'nearest',
    nodata: float = None,
    n_threads: int = 5,
    dtype: str | np.dtype = None,
) -> tuple[np.ndarray, dict]:
    # 4269 is North American epsg similar to 4326 and used for 3dep DEM
    inputs_str = isinstance(datasets[0], str)
    if inputs_str:
        datasets_objs = [rasterio.open(ds_path) for ds_path in datasets]
    else:
        datasets_objs = datasets

    if datasets_objs[0].profile['crs'] not in [CRS.from_epsg(4326), CRS.from_epsg(4269)]:
        raise ValueError('CRS must be epgs:4326')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        datasets_filtered = [
            ds
            for ds in datasets_objs
            if (
                box(*ds.bounds).intersects(box(*extent))
                and (box(*ds.bounds).intersection(box(*extent)).geom_type == 'Polygon')
            )
        ]

    src_profiles = [ds.profile for ds in datasets_filtered]

    def window_partial(profile: dict) -> Window:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            window = get_window_from_extent(profile, extent, window_crs=CRS.from_epsg(4326))
        return window

    def read_in_window(dataset: rasterio.DatasetReader, window: rasterio.windows.Window) -> np.ndarray:
        return dataset.read(window=window)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
        windows = list(
            tqdm(executor.map(window_partial, src_profiles[:]), total=len(src_profiles), desc='Reading tile metadata')
        )
        assert len(datasets_filtered) == len(windows), 'input_lengths of datasets and windows not aligned'
        arrs_window = list(
            tqdm(
                executor.map(read_in_window, datasets_filtered, windows),
                total=len(windows),
                desc='Reading tile imagery',
            )
        )

    # arrs_window = [ds.read(window=window) for (ds, window) in zip(datasets_filtered, windows)]
    if dtype is not None:
        arrs_window = [arr.astype(dtype) for arr in arrs_window]
    trans_window = [ds.window_transform(window=window) for (ds, window) in zip(datasets_filtered, windows)]
    profs_window = [
        format_window_profile(p_s, arr_w, tran_w)
        for (p_s, arr_w, tran_w) in zip(src_profiles, arrs_window, trans_window)
    ]

    arr_merged, prof_merged = merge_arrays_with_geometadata(
        arrs_window, profs_window, resampling=resampling, method='first', nodata=nodata, dtype=dtype
    )
    if inputs_str:
        [ds.close() for ds in datasets_objs]
    return arr_merged, prof_merged


def _integer_pixel_offset(value: float) -> int | None:
    offset = round(value)
    return offset if abs(value - offset) < 1e-6 else None


def _aligned_pixel_offsets(profiles: list[dict]) -> list[tuple[int | None, int | None]] | None:
    t_ref = profiles[0]['transform']
    transforms = [p['transform'] for p in profiles]
    north_up = all(t.b == 0 and t.d == 0 and t.a > 0 and t.e < 0 for t in transforms)
    same_crs = all(p['crs'] == profiles[0]['crs'] for p in profiles)
    same_res = all(
        math.isclose(t.a, t_ref.a, rel_tol=1e-9) and math.isclose(t.e, t_ref.e, rel_tol=1e-9) for t in transforms
    )
    if not (north_up and same_crs and same_res):
        return None
    offsets = [
        (_integer_pixel_offset((t.f - t_ref.f) / t_ref.e), _integer_pixel_offset((t.c - t_ref.c) / t_ref.a))
        for t in transforms
    ]
    return None if any(None in offset for offset in offsets) else offsets


def _nodata_representable(nodataval: float, dt: np.dtype) -> bool:
    if np.issubdtype(dt, np.integer):
        info = np.iinfo(dt)
        return bool(info.min <= nodataval <= info.max)
    if math.isfinite(nodataval):
        info = np.finfo(dt)
        return bool(info.min <= nodataval <= info.max) and np.can_cast(np.min_scalar_type(nodataval), dt)
    return True


def _merge_aligned_arrays(
    arrays: list[np.ndarray],
    profiles: list[dict],
    nodata: float | None,
    dtype: str | np.dtype,
    method: str,
) -> tuple[np.ndarray, Affine] | None:
    """Composite pixel-aligned arrays with numpy, mirroring `rasterio.merge.merge`.

    Applies when all arrays share a CRS, resolution, and pixel-congruent origins - then merging is index
    arithmetic and `rasterio.merge` would never resample. Reuses rasterio's own per-method compositing
    functions (`MERGE_METHODS`) so the semantics are identical; only the in-memory GTiff round-trip is
    skipped. Returns None when the grids are not aligned so the caller can fall back to `rasterio.merge`.
    """
    offsets = _aligned_pixel_offsets(profiles)
    if offsets is None:
        return None
    dt = np.dtype(dtype)
    if nodata is not None and not _nodata_representable(nodata, dt):
        return None
    nodataval = 0 if nodata is None else nodata

    copyto = MERGE_METHODS[method]
    t_ref = profiles[0]['transform']
    row_offs, col_offs = zip(*offsets)
    row_min, col_min = min(row_offs), min(col_offs)
    height = max(r - row_min + arr.shape[1] for r, arr in zip(row_offs, arrays))
    width = max(c - col_min + arr.shape[2] for c, arr in zip(col_offs, arrays))

    dest = np.full((arrays[0].shape[0], height, width), nodataval, dtype=dt)
    for arr, profile, (row_off, col_off) in zip(arrays, profiles, offsets):
        data = np.asarray(arr, dtype=np.dtype(profile['dtype']))
        rows = slice(row_off - row_min, row_off - row_min + data.shape[1])
        cols = slice(col_off - col_min, col_off - col_min + data.shape[2])
        region = dest[:, rows, cols]
        if math.isnan(nodataval):
            region_mask = np.isnan(region)
        elif np.issubdtype(dt, np.integer):
            region_mask = region == nodataval
        else:
            region_mask = np.isclose(region, nodataval)
        src_nodata = profile['nodata']
        if src_nodata is None:
            data_mask = np.zeros(data.shape, dtype=bool)
        elif math.isnan(src_nodata):
            data_mask = np.isnan(data)
        else:
            data_mask = data == src_nodata
        copyto(region, data, region_mask, data_mask)

    merged_transform = Affine.translation(t_ref.c + col_min * t_ref.a, t_ref.f + row_min * t_ref.e) * Affine.scale(
        t_ref.a, t_ref.e
    )
    return dest, merged_transform


def merge_arrays_with_geometadata(
    arrays: list[np.ndarray],
    profiles: list[dict],
    resampling: str = 'bilinear',
    nodata: float = None,
    dtype: str = None,
    method: str = 'first',
) -> tuple[np.ndarray, dict]:
    """Merge arrays in memory with geometadata.

    Parameters
    ----------
    arrays : list[np.ndarray]
        Arrays to merge (must be in the same CRS)
    profiles : list[dict]
        Geometadata for each array
    resampling : str, optional
        See acceptable values rasterio.enums.Resampling, by default 'bilinear'
    nodata : float, optional
        Nodata value to be inserted into merged profile. If None, uses the nodata value from the first profile,
        by default None
    dtype : str, optional
        Dtype to be inserted into merged profile. If None, uses the dtype from the first profile, by default None
    method : str, optional
        See acceptable values in rasterio.merge.merge, by default 'first'

    Returns
    -------
    tuple[np.ndarray, dict]
        Merged array and profile

    Raises
    ------
    ValueError
        * If arrays are not in BIP format
        * If arrays have different number of dimensions (i.e. 2 or 3)
        * If number of profiles is not the same as number of arrays
    """
    n_dim = arrays[0].shape
    if len(n_dim) not in [2, 3]:
        raise ValueError('Currently arrays must be in BIP formati.e. channels x height x width or flat array')
    if len(set([len(arr.shape) for arr in arrays])) != 1:
        raise ValueError('All arrays must have same number of dimensions i.e. 2 or 3')

    if len(n_dim) == 2:
        arrays_input = [arr[np.newaxis, ...] for arr in arrays]
    else:
        arrays_input = arrays

    if (len(arrays)) != (len(profiles)):
        raise ValueError('Length of arrays and profiles needs to be the same')

    if dtype is None:
        dst_dtype = profiles[0]['dtype']
    else:
        dst_dtype = dtype

    if nodata is None:
        dst_nodata = profiles[0]['nodata']
    else:
        dst_nodata = nodata

    merged = None
    if method in MERGE_METHODS:
        merged = _merge_aligned_arrays(arrays_input, profiles, dst_nodata, dst_dtype, method)

    if merged is not None:
        merged_arr, merged_trans = merged
    else:
        memfiles = [MemoryFile() for p in profiles]
        datasets = [mfile.open(**in_memory_profile(p)) for (mfile, p) in zip(memfiles, profiles)]
        [ds.write(arr) for (ds, arr) in zip(datasets, arrays_input)]
        merged_arr, merged_trans = merge(
            datasets, resampling=Resampling[resampling], method=method, nodata=dst_nodata, dtype=dst_dtype
        )
        [ds.close() for ds in datasets]
        [mfile.close() for mfile in memfiles]

    prof_merged = profiles[0].copy()
    prof_merged['transform'] = merged_trans
    prof_merged['count'] = merged_arr.shape[0]
    prof_merged['height'] = merged_arr.shape[1]
    prof_merged['width'] = merged_arr.shape[2]
    prof_merged['nodata'] = dst_nodata
    prof_merged['dtype'] = dst_dtype

    return merged_arr, prof_merged
