import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import array_bounds

from .datasets import DATA_PATH
from .rio_tools import reproject_arr_to_match_profile, translate_profile
from .rio_window import read_raster_from_window

AGISOFT_URL = 'http://download.agisoft.com/geoids'
GEOID_PATHS_AGI = {'geoid_18': f'{DATA_PATH}/geoid_18.tif',
                   'egm_08': f'{AGISOFT_URL}/egm2008-1.tif',
                   'egm_96': f'{AGISOFT_URL}/egm96-15.tif'}


def get_geoid_dict() -> dict:
    geoid_dict = GEOID_PATHS_AGI
    return geoid_dict.copy()


def read_geoid(geoid_name: str,
               extent: list = None,
               buffer: float = .05) -> tuple:

    geoid_dict = get_geoid_dict()
    geoid_path = geoid_dict[geoid_name]

    if extent is None:
        with rasterio.open(geoid_path) as ds:
            geoid_arr = ds.read(1)
            geoid_profile = ds.profile
    else:
        crs = CRS.from_epsg(4326)
        geoid_arr, geoid_profile = read_raster_from_window(geoid_path,
                                                           extent,
                                                           crs,
                                                           buffer=buffer,
                                                           min_res_buffer=1)

    return geoid_arr, geoid_profile


def remove_geoid(dem_arr: np.ndarray,
                 dem_profile: dict,
                 geoid_name: str,
                 extent: list = None,
                 dem_area_or_point: str = 'Point') -> np.ndarray:

    assert(dem_area_or_point in ['Point', 'Area'])

    extent = array_bounds(dem_profile['height'],
                          dem_profile['width'],
                          dem_profile['transform'])

    # make list a tuple, so we can still cache results
    geoid_arr, geoid_profile = read_geoid(geoid_name,
                                          extent=extent,
                                          buffer=0.05)

    geoid_offset, _ = reproject_arr_to_match_profile(geoid_arr,
                                                     geoid_profile,
                                                     dem_profile,
                                                     resampling='bilinear')

    # Translate geoid if necessary
    if dem_area_or_point == 'Point':
        shift = -.5
        geoid_profile = translate_profile(geoid_profile,
                                          shift, shift)

    geoid_offset = geoid_offset[0, ...]
    dem_arr_offset = dem_arr + geoid_offset
    return dem_arr_offset
