import warnings

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
               res_buffer: int = 1) -> tuple:

    if ((extent is not None) and
       ((extent[0] < -180) or (extent[2] > 180) or (extent[1] < -90) or (extent[3] > 90))):
        raise ValueError('Extent should be in lon/lat as xmin, ymin, xmax, ymax')

    geoid_dict = get_geoid_dict()
    geoid_path = geoid_dict[geoid_name]

    if extent is None:
        with rasterio.open(geoid_path) as ds:
            geoid_arr = ds.read(1)
            geoid_profile = ds.profile
    else:
        extent_crs = CRS.from_epsg(4326)
        geoid_arr, geoid_profile = read_raster_from_window(geoid_path,
                                                           extent,
                                                           extent_crs,
                                                           res_buffer=res_buffer)
    # Transform nodata to nan
    geoid_arr = geoid_arr.astype('float32')
    geoid_arr[geoid_profile['nodata'] == geoid_arr] = np.nan
    geoid_profile['nodata'] = np.nan

    return geoid_arr, geoid_profile


def remove_geoid(dem_arr: np.ndarray,
                 dem_profile: dict,
                 geoid_name: str,
                 dem_area_or_point: str = 'Area',
                 res_buffer: int = 2) -> np.ndarray:

    assert(dem_area_or_point in ['Point', 'Area'])

    extent = array_bounds(dem_profile['height'],
                          dem_profile['width'],
                          dem_profile['transform'])

    geoid_arr, geoid_profile = read_geoid(geoid_name,
                                          extent=list(extent),
                                          res_buffer=res_buffer)

    t_dem = dem_profile['transform']
    t_geoid = geoid_profile['transform']
    res_dem = max(t_dem.a, abs(t_dem.e))
    res_geoid = max(t_geoid.a, abs(t_geoid.e))

    if res_geoid * res_buffer <= res_dem:
        buffer_recommendation = int(np.ceil(res_dem / res_geoid))
        warning = ('The dem resolution is larger than the geoid resolution and its buffer; '
                   'Edges resampled with bilinear interpolation will be inconsistent so select larger buffer.'
                   f'Select a `res_buffer = {buffer_recommendation}`')
        warnings.warn(warning, category=UserWarning)

    # Translate geoid if necessary as all geoids have Area tag
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
