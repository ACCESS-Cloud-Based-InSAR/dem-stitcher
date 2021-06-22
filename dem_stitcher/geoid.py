import rasterio
from functools import lru_cache
import numpy as np
from rasterio.crs import CRS
from .rio_tools import reproject_arr_to_match_profile, translate_profile
from .datasets import DATA_PATH
from .rio_window import read_raster_from_window

GEOID_PATHS = {'geoid_18': DATA_PATH/'geoid_18.tif',
               'egm_08': 'http://download.agisoft.com/geoids/egm2008-1.tif',
               'egm_96': 'http://download.agisoft.com/geoids/egm96-15.tif'}


@lru_cache
def read_geoid(geoid_name: str, extent: tuple = None) -> tuple:

    geoid_path = GEOID_PATHS[geoid_name]

    if extent is None:
        with rasterio.open(geoid_path) as ds:
            geoid_arr = ds.read(1)
            geoid_profile = ds.profile
    else:
        crs = CRS.from_epsg(4326)
        geoid_arr, geoid_profile = read_raster_from_window(geoid_path,
                                                           extent,
                                                           crs,
                                                           buffer=.05)

    return geoid_arr, geoid_profile


def remove_geoid(dem_arr: np.ndarray,
                 dem_profile: dict,
                 geoid_name: str,
                 extent: list = None,
                 dem_area_or_point: str = 'Point'):

    assert(dem_area_or_point in ['Point', 'Area'])

    # if empty string or None, do nothing
    if not geoid_name:
        return dem_arr

    # make list a tuple, so we can still cache results
    geoid_arr, geoid_profile = read_geoid(geoid_name, extent=tuple(extent))

    # Translate geoid if necessary
    if dem_area_or_point == 'Point':
        shift = -.5
        geoid_profile = translate_profile(geoid_profile,
                                          shift, shift)

    geoid_offset, _ = reproject_arr_to_match_profile(geoid_arr,
                                                     geoid_profile,
                                                     dem_profile,
                                                     resampling='bilinear')
    geoid_offset = geoid_offset[0, ...]
    dem_arr_offset = dem_arr + geoid_offset
    return dem_arr_offset
