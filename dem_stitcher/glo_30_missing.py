from typing import Tuple

import numpy as np
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge


def merge_glo_30_and_90_dems(arr_glo_30,
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
