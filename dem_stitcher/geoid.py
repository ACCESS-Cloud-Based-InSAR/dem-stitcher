import numpy as np
import rasterio
from rasterio.transform import array_bounds

from .datasets import DATA_PATH

AGISOFT_URL = 'http://download.agisoft.com/geoids'
GEOID_PATHS_AGI = {'geoid_18': f'{DATA_PATH}/geoid_18.tif',
                   'egm_08': f'{AGISOFT_URL}/egm2008-1.tif',
                   'egm_96': f'{AGISOFT_URL}/egm96-15.tif'}


def get_geoid_dict() -> dict:
    geoid_dict = GEOID_PATHS_AGI
    return geoid_dict.copy()


def read_geoid(geoid_name: str,
               extent: list = None,
               res: float = None,
               filepath: str = None
               ) -> tuple:
    from dem_stitcher.stitcher import gdal_merge_tiles

    geoid_dict = get_geoid_dict()
    geoid_path = geoid_dict[geoid_name]

    with rasterio.open(geoid_path) as ds:
        geoid_profile = ds.profile

    nodata = np.nan
    if str(geoid_profile['dtype']) == 'int16':
        nodata = geoid_profile['nodata']

    geoid_arr, geoid_profile = gdal_merge_tiles([f'/vsicurl/{geoid_path}'],
                                                res,
                                                bounds=extent,
                                                nodata=nodata,
                                                filepath=filepath+'.geoid',
                                                resampling='bilinear')

    return geoid_arr, geoid_profile


def remove_geoid(dem_arr: np.ndarray,
                 dem_profile: dict,
                 geoid_name: str,
                 extent: list = None,
                 src_area_or_point: str = 'Point',
                 dem_area_or_point: str = 'Point',
                 filepath: str = None
                 ) -> np.ndarray:
    import os
    import glob
    from dem_stitcher.stitcher import gdal_shift_profile_for_pixel_loc

    assert(dem_area_or_point in ['Point', 'Area'])

    # make list a tuple, so we can still cache results
    geoid_arr, geoid_profile = read_geoid(geoid_name,
                                          extent=extent,
                                          res=dem_profile['transform'][0],
                                          filepath=filepath)

    geoid_arr, geoid_profile = gdal_shift_profile_for_pixel_loc(f'{filepath}.geoid',
                                                                src_area_or_point,
                                                                dem_area_or_point,
                                                                geoid_arr,
                                                                geoid_profile)

    dem_arr_offset = dem_arr + geoid_arr

    # remove temp files
    for i in glob.glob(filepath+'.geoid*'):
        os.remove(i)

    return dem_arr_offset
