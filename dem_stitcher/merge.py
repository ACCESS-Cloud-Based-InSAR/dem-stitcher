from typing import List, Tuple

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge

from .rio_window import get_indices_from_extent


def merge_tile_datasets(datasets: List[rasterio.DatasetReader],
                        bounds: list = None,
                        resampling: str = 'nearest',
                        res_buffer: int = 0,
                        nodata: float = np.nan
                        ) -> Tuple[np.ndarray, dict]:
    merged_arr, merged_transform = merge(datasets,
                                         resampling=Resampling[resampling],
                                         # This fixes the nodata values
                                         nodata=nodata,
                                         # This fixes the float32 output
                                         dtype='float32',
                                         )
    merged_arr = merged_arr[0, ...]

    # each pair is in (row, col) format
    corner_ul, corner_br = get_indices_from_extent(merged_transform,
                                                   bounds,
                                                   shape=merged_arr.shape,
                                                   res_buffer=res_buffer)
    sy = np.s_[corner_ul[0]: corner_br[0]]
    sx = np.s_[corner_ul[1]: corner_br[1]]
    merged_arr = merged_arr[sy, sx]

    # We swap row and columns because Affine expects (x, y) or (col, row)
    origin_affine = corner_ul[1], corner_ul[0]
    new_origin = merged_transform * origin_affine
    merged_transform_final = Affine.translation(*new_origin)
    merged_transform_final = merged_transform_final * Affine.scale(merged_transform.a,
                                                                   merged_transform.e)

    merged_profile = datasets[0].profile.copy()
    merged_profile['height'] = merged_arr.shape[0]
    merged_profile['width'] = merged_arr.shape[1]
    merged_profile['nodata'] = np.nan
    merged_profile['dtype'] = 'float32'
    merged_profile['transform'] = merged_transform_final
    return merged_arr, merged_profile


def merge_arrays_with_geometadata(arrays: List[np.ndarray],
                                  profiles: List[dict],
                                  resampling='bilinear',
                                  method='first') -> Tuple[np.ndarray, dict]:

    if len(arrays[0].shape) > 2:
        raise ValueError('Currently only supports 2d arrays')

    if (len(arrays)) != (len(profiles)):
        raise ValueError('Length of arrays and profiles needs to be the same')

    memfiles = [MemoryFile() for p in profiles]
    datasets = [mfile.open(**p) for (mfile, p) in zip(memfiles, profiles)]
    [ds.write(arr, 1) for (ds, arr) in zip(datasets, arrays)]

    merged_arr, merged_trans = merge(datasets,
                                     resampling=Resampling[resampling],
                                     method=method,
                                     )
    merged_arr = merged_arr[0, ...]

    prof_merged = profiles[0].copy()
    prof_merged['transform'] = merged_trans
    prof_merged['width'] = merged_arr.shape[1]
    prof_merged['height'] = merged_arr.shape[0]

    [ds.close() for ds in datasets]
    [mfile.close() for mfile in memfiles]

    return merged_arr, prof_merged
