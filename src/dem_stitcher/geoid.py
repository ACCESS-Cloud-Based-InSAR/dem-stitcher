import warnings
from pathlib import Path
from typing import Union

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import array_bounds

from .datasets import DATA_PATH
from .dateline import get_dateline_crossing, split_extent_across_dateline
from .merge import merge_arrays_with_geometadata
from .rio_tools import reproject_arr_to_match_profile, translate_profile
from .rio_window import read_raster_from_window


DEM2GEOID = {
    '3dep': 'geoid_18',
    'glo_30': 'egm_08',
    'glo_90': 'egm_08',
    'glo_90_missing': 'egm_08',
    'srtm_v3': 'egm_96',
    'nasadem': 'egm_96',
}

ARIA_GEOIDS = 'https://aria-geoid.s3.us-west-2.amazonaws.com'
GEOID_PATHS_AGI = {
    'geoid_18': f'{DATA_PATH}/geoid_18.tif',
    'egm_08': f'{ARIA_GEOIDS}/us_nga_egm2008_1_4326__agisoft.tif',
    'egm_96': f'{DATA_PATH}/egm96_15.gtx',
}


def get_geoid_dict() -> dict:
    geoid_dict = GEOID_PATHS_AGI
    return geoid_dict.copy()


def get_geoid_path(geoid_short_name: str) -> Path:
    geoid_path = GEOID_PATHS_AGI[geoid_short_name]
    return geoid_path


def get_default_geoid_path(dem_name: Union[str, Path]) -> Path:
    if dem_name not in DEM2GEOID.keys():
        raise ValueError(f'DEM name {dem_name} does not have a default geoid.')
    geoid_name = DEM2GEOID[dem_name]
    geoid_path = get_geoid_path(geoid_name)
    return geoid_path


def validate_geoid_path(geoid_path: Union[str, Path]) -> None:
    if isinstance(geoid_path, str):
        if geoid_path in DEM2GEOID.values():
            return
        elif geoid_path.startswith('https') or geoid_path.startswith('s3://'):
            return
        else:
            geoid_path = Path(geoid_path)
            if not geoid_path.exists():
                raise FileNotFoundError(f'Geoid file {geoid_path} does not exist.')
            return
    elif isinstance(geoid_path, Path):
        if not geoid_path.exists():
            raise FileNotFoundError(f'Geoid file {geoid_path} does not exist.')
    raise TypeError(f'Geoid path {geoid_path} is not of type str or Path.')


def read_geoid(geoid_path: Union[str, Path], extent: Union[list, None] = None, res_buffer: int = 1) -> tuple:
    if extent is None:
        with rasterio.open(geoid_path) as ds:
            geoid_arr = ds.read()
            geoid_profile = ds.profile
    else:
        extent_crs = CRS.from_epsg(4326)
        crossing = get_dateline_crossing(extent)

        if crossing == 0:
            geoid_arr, geoid_profile = read_raster_from_window(geoid_path, extent, extent_crs, res_buffer=res_buffer)
        else:
            with rasterio.open(geoid_path) as ds:
                xmin, _, xmax, _ = ds.bounds
                if xmin > -180 or xmax < 180:
                    warnings.warn(
                        'Geoid file does not cover the dateline. May have np.nan values after removal'
                        ' or unexpected behavior. Recommend using geoid with 1 pixel buffer around dateline.',
                        category=UserWarning,
                    )
            extent_l, extent_r = split_extent_across_dateline(extent)
            geoid_arr_l, geoid_profile_l = read_raster_from_window(
                geoid_path, extent_l, extent_crs, res_buffer=res_buffer
            )
            geoid_arr_r, geoid_profile_r = read_raster_from_window(
                geoid_path, extent_r, extent_crs, res_buffer=res_buffer
            )
            res_x = geoid_profile_l['transform'].a
            if crossing == 180:
                geoid_profile_l = translate_profile(geoid_profile_l, 360 / res_x, 0)
            else:
                geoid_profile_r = translate_profile(geoid_profile_r, -360 / res_x, 0)
            geoid_arr, geoid_profile = merge_arrays_with_geometadata(
                [geoid_arr_l, geoid_arr_r], [geoid_profile_l, geoid_profile_r]
            )
    # Transform nodata to nan
    geoid_arr = geoid_arr.astype('float32')
    geoid_arr[geoid_profile['nodata'] == geoid_arr] = np.nan
    geoid_profile['nodata'] = np.nan

    return geoid_arr, geoid_profile


def remove_geoid(
    dem_arr: np.ndarray,
    dem_profile: dict,
    geoid_path: Union[str, Path],
    dem_area_or_point: str = 'Area',
    res_buffer: int = 2,
) -> np.ndarray:
    assert dem_area_or_point in ['Point', 'Area']

    extent = array_bounds(dem_profile['height'], dem_profile['width'], dem_profile['transform'])

    validate_geoid_path(geoid_path)
    geoid_arr, geoid_profile = read_geoid(geoid_path, extent=list(extent), res_buffer=res_buffer)

    t_dem = dem_profile['transform']
    t_geoid = geoid_profile['transform']
    res_dem = max(t_dem.a, abs(t_dem.e))
    res_geoid = max(t_geoid.a, abs(t_geoid.e))

    if res_geoid * res_buffer <= res_dem:
        buffer_recommendation = int(np.ceil(res_dem / res_geoid))
        warning = (
            'The dem resolution is larger than the geoid resolution and its buffer; '
            'Edges resampled with bilinear interpolation will be inconsistent so select larger buffer.'
            f'Select a `res_buffer = {buffer_recommendation}`'
        )
        warnings.warn(warning, category=UserWarning)

    # Translate geoid if necessary as all geoids have Area tag
    if dem_area_or_point == 'Point':
        shift = -0.5
        geoid_profile = translate_profile(geoid_profile, shift, shift)

    geoid_offset, _ = reproject_arr_to_match_profile(geoid_arr, geoid_profile, dem_profile, resampling='bilinear')

    dem_arr_offset = dem_arr + geoid_offset
    return dem_arr_offset
