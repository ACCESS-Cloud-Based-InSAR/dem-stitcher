import warnings
from typing import Union

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.windows import Window
from shapely.geometry import box

from .rio_window import format_window_profile, get_window_from_extent


def merge_tile_datasets_within_extent(datasets: Union[list[rasterio.DatasetReader], list[str]],
                                      extent: list,
                                      resampling: str = 'nearest',
                                      nodata: float = None,
                                      dtype: Union[str, np.dtype] = None
                                      ) -> tuple[np.ndarray, dict]:
    # 4269 is North American epsg similar to 4326 and used for 3dep DEM
    inputs_str = isinstance(datasets[0], str)
    if inputs_str:
        datasets_objs = [rasterio.open(ds_path) for ds_path in datasets]
    else:
        datasets_objs = datasets

    if datasets_objs[0].profile['crs'] not in [CRS.from_epsg(4326), CRS.from_epsg(4269)]:
        raise ValueError('CRS must be epgs:4326')

    datasets_filtered = [ds for ds in datasets_objs
                         if (box(*ds.bounds).intersects(box(*extent)) and
                             (box(*ds.bounds).intersection(box(*extent)).geom_type == 'Polygon')
                             )
                         ]

    src_profiles = [ds.profile for ds in datasets_filtered]

    def window_partial(profile: dict) -> Window:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            return get_window_from_extent(profile,
                                          extent,
                                          window_crs=CRS.from_epsg(4326))
    windows = [window_partial(p) for p in src_profiles]
    arrs_window = [ds.read(window=window) for (ds, window) in zip(datasets_filtered, windows)]
    if dtype is not None:
        arrs_window = [arr.astype(dtype) for arr in arrs_window]
    trans_window = [ds.window_transform(window=window) for (ds, window) in zip(datasets_filtered, windows)]
    profs_window = [format_window_profile(p_s, arr_w, tran_w)
                    for (p_s, arr_w, tran_w) in zip(src_profiles, arrs_window, trans_window)]

    arr_merged, prof_merged = merge_arrays_with_geometadata(arrs_window,
                                                            profs_window,
                                                            resampling=resampling,
                                                            method='first',
                                                            nodata=nodata,
                                                            dtype=dtype)
    if inputs_str:
        [ds.close() for ds in datasets_objs]
    return arr_merged, prof_merged


def merge_arrays_with_geometadata(arrays: list[np.ndarray],
                                  profiles: list[dict],
                                  resampling='bilinear',
                                  nodata: Union[float, int] = np.nan,
                                  dtype: str = None,
                                  method='first') -> tuple[np.ndarray, dict]:

    n_dim = arrays[0].shape
    if len(n_dim) not in [2, 3]:
        raise ValueError('Currently arrays must be in BIP format'
                         'i.e. channels x height x width or flat array')
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

    merged_arr, merged_trans = merge(datasets,
                                     resampling=Resampling[resampling],
                                     method=method,
                                     nodata=nodata,
                                     dtype=dtype
                                     )

    prof_merged = profiles[0].copy()
    prof_merged['transform'] = merged_trans
    prof_merged['count'] = merged_arr.shape[0]
    prof_merged['height'] = merged_arr.shape[1]
    prof_merged['width'] = merged_arr.shape[2]
    if nodata is not None:
        prof_merged['nodata'] = nodata
    if nodata is not None:
        prof_merged['dtype'] = dtype

    [ds.close() for ds in datasets]
    [mfile.close() for mfile in memfiles]

    return merged_arr, prof_merged
