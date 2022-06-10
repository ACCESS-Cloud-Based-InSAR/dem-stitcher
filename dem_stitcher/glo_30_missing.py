from typing import Tuple

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from shapely.geometry import box

from .stitcher import get_dem_tile_extents, stitch_dem


def intersect_missing_glo_30_tiles(extent: list) -> bool:
    df_missing = get_dem_tile_extents('glo_90_missing')
    extent_geo = box(*extent)
    return df_missing.intersects(extent_geo).sum() > 0


def _merge_glo_30_and_90_dems(arr_glo_30,
                              prof_glo_30,
                              arr_glo_90,
                              prof_glo_90) -> Tuple[np.ndarray, dict]:
    with MemoryFile() as memfile_90:
        dataset_90 = memfile_90.open(**prof_glo_90)
        dataset_90.write(arr_glo_90, 1)

        with MemoryFile() as memfile_30:
            dataset_30 = memfile_30.open(**prof_glo_30)
            dataset_30.write(arr_glo_30, 1)

            merged_arr, merged_trans = merge([dataset_30, dataset_90],
                                             resampling=Resampling['bilinear'],
                                             method='first',
                                             )
            merged_glo_arr = merged_arr[0, ...]

    prof_30_merged = prof_glo_30.copy()
    prof_30_merged['transform'] = merged_trans
    prof_30_merged['width'] = merged_glo_arr.shape[1]
    prof_30_merged['height'] = merged_glo_arr.shape[0]

    return merged_glo_arr, prof_30_merged


def patch_glo_30_with_glo_90(arr_glo_30: np.ndarray,
                             prof_glo_30: dict,
                             extent: list,
                             stitcher_kwargs: dict) -> Tuple[np.ndarray, dict]:
    if not intersect_missing_glo_30_tiles(extent):
        return arr_glo_30, prof_glo_30

    stitcher_kwargs['dem_name'] = 'glo_90_missing'
    # if dst_resolution is None, then make sure we upsample to 30 meter resolution
    dst_resolution = stitcher_kwargs['dst_resolution']
    stitcher_kwargs['dst_resolution'] = dst_resolution or 0.0002777777777777777775

    arr_glo_90, prof_glo_90 = stitch_dem(**stitcher_kwargs)

    dem_arr, dem_prof = _merge_glo_30_and_90_dems(arr_glo_30,
                                                  prof_glo_30,
                                                  arr_glo_90,
                                                  prof_glo_90
                                                  )

    return dem_arr, dem_prof
