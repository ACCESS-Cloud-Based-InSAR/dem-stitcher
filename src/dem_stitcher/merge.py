import warnings
from typing import Union

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import copy_first, merge
from shapely.geometry import box
from tqdm import tqdm

from .rio_window import get_window_from_extent


def _union_of_tile_windows(
    datasets: list[rasterio.DatasetReader], extent: list[float]
) -> tuple[float, float, float, float]:
    xmin = ymin = float('inf')
    xmax = ymax = float('-inf')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        for ds in datasets:
            w = get_window_from_extent(ds.profile, extent, window_crs=ds.crs)
            left, bottom, right, top = ds.window_bounds(w)
            xmin = min(xmin, left)
            ymin = min(ymin, bottom)
            xmax = max(xmax, right)
            ymax = max(ymax, top)
    return (xmin, ymin, xmax, ymax)


def merge_tile_datasets_within_extent(
    datasets: Union[list[rasterio.DatasetReader], list[str]],
    extent: list,
    resampling: str = 'nearest',
    nodata: float = None,
    n_threads: int = 5,
    dtype: Union[str, np.dtype] = None,
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

    if not datasets_filtered:
        raise ValueError('No datasets intersect requested extent')

    src_profile = datasets_filtered[0].profile.copy()
    dst_dtype = src_profile['dtype'] if dtype is None else dtype
    dst_nodata = src_profile['nodata'] if nodata is None else nodata

    # Snap merge bounds outward to each tile's pixel grid so output dimensions
    # match the old windowed-read path (extent typically exceeds individual tiles,
    # so the per-tile "shrinking bounds" warnings are suppressed internally).
    merge_bounds = _union_of_tile_windows(datasets_filtered, extent)

    with tqdm(total=len(datasets_filtered), desc='Reading tile imagery') as pbar:

        def _copy_first_progress(*args: object, **kwargs: object) -> None:
            copy_first(*args, **kwargs)
            pbar.update(1)

        with rasterio.Env(GDAL_NUM_THREADS=n_threads):
            arr_merged, merged_transform = merge(
                datasets_filtered,
                bounds=merge_bounds,
                resampling=Resampling[resampling],
                method=_copy_first_progress,
                nodata=dst_nodata,
                dtype=dst_dtype,
            )

    prof_merged = src_profile.copy()
    prof_merged.update(
        transform=merged_transform,
        count=arr_merged.shape[0],
        height=arr_merged.shape[1],
        width=arr_merged.shape[2],
        nodata=dst_nodata,
        dtype=dst_dtype,
    )

    if inputs_str:
        [ds.close() for ds in datasets_objs]
    return arr_merged, prof_merged


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

    memfiles = [MemoryFile() for p in profiles]
    datasets = [mfile.open(**p) for (mfile, p) in zip(memfiles, profiles)]
    [ds.write(arr) for (ds, arr) in zip(datasets, arrays_input)]

    if dtype is None:
        dst_dtype = profiles[0]['dtype']
    else:
        dst_dtype = dtype

    if nodata is None:
        dst_nodata = profiles[0]['nodata']
    else:
        dst_nodata = nodata

    merged_arr, merged_trans = merge(
        datasets, resampling=Resampling[resampling], method=method, nodata=dst_nodata, dtype=dst_dtype
    )

    prof_merged = profiles[0].copy()
    prof_merged['transform'] = merged_trans
    prof_merged['count'] = merged_arr.shape[0]
    prof_merged['height'] = merged_arr.shape[1]
    prof_merged['width'] = merged_arr.shape[2]
    prof_merged['nodata'] = dst_nodata
    prof_merged['dtype'] = dst_dtype

    [ds.close() for ds in datasets]
    [mfile.close() for mfile in memfiles]

    return merged_arr, prof_merged
