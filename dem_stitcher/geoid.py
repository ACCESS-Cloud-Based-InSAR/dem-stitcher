import rasterio
import numpy as np
import requests
from rasterio.crs import CRS
from .rio_tools import reproject_arr_to_match_profile, translate_profile
from .datasets import DATA_PATH
from .rio_window import read_raster_from_window

S3_URL = 'https://aria-dev-lts-fwd-torresal.s3.us-west-2.amazonaws.com'
GEOID_PATHS_JPL = {'geoid_18': f'{DATA_PATH}/geoid_18.tif',
                   'egm_08': f'{S3_URL}/datasets/geoid/egm2008-1.tif',
                   'egm_96': f'{S3_URL}/datasets/geoid/egm96-15.tif'}

AGISOFT_URL = 'http://download.agisoft.com/geoids'
GEOID_PATHS_AGI = {'egm_08': f'{AGISOFT_URL}/egm2008-1.tif',
                   'egm_96': f'{AGISOFT_URL}/egm96-15.tif'}


def get_geoid_dict() -> dict:
    """Check if on the JPL network. Otherwise use the AGI urls

    Returns
    -------
    dict
        The appropriate above hard-coded dictionary with urls.
    """
    geoid_dict = GEOID_PATHS_AGI

    resp = requests.head(S3_URL)
    if resp.status_code == 200:
        geoid_dict = GEOID_PATHS_JPL

    return geoid_dict.copy()


def read_geoid(geoid_name: str,
               extent: tuple = None,
               force_agi_read: bool = False) -> tuple:

    geoid_dict = get_geoid_dict()

    # force the use of AGI endpoint even on the JPL VPN
    if force_agi_read:
        geoid_dict = GEOID_PATHS_AGI.copy()

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
                                                           buffer=.05)

    return geoid_arr, geoid_profile


def remove_geoid(dem_arr: np.ndarray,
                 dem_profile: dict,
                 geoid_name: str,
                 extent: list = None,
                 dem_area_or_point: str = 'Point',
                 force_agi_read: bool = False) -> np.ndarray:

    assert(dem_area_or_point in ['Point', 'Area'])

    # if empty string or None, do nothing
    if not geoid_name:
        return dem_arr

    # make list a tuple, so we can still cache results
    geoid_arr, geoid_profile = read_geoid(geoid_name,
                                          extent=tuple(extent),
                                          force_agi_read=force_agi_read)

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
