from functools import lru_cache
from pathlib import Path
from warnings import warn

import geopandas as gpd
import pandas as pd
from rasterio.crs import CRS
from shapely.geometry import box

from .dateline import check_4326_bounds, get_dateline_crossing
from .exceptions import DEMNotSupported
from .geojson_io import read_geojson_gzip

DATA_PATH = Path(__file__).parents[0].absolute()/'data'

# Get Datasets
_DATASET_PATHS = list(DATA_PATH.glob('*.geojson.zip'))
DATASETS = list(map(lambda x: x.name.split('.')[0], _DATASET_PATHS))


def get_available_datasets():
    return DATASETS


# TODO: maxsize=None is not needed for 3.8+
@lru_cache(maxsize=None)
def get_global_dem_tile_extents(dataset: str) -> gpd.GeoDataFrame:
    """Obtains globally avaialable tiles from DEM names supported.

    Parameters
    ----------
    dataset : str
        A DEM name supported e.g. 'glo_30', 'glo_90', 'nasadem'

    Returns
    -------
    gpd.GeoDataFrame
        Columns are `tile_id`, `url`, `geometry` and `dem_name`

    Raises
    ------
    DEMNotSupported
        Dataset is not supported.
    """
    if dataset not in DATASETS:
        raise DEMNotSupported(f'{dataset} must be in {", ".join(DATASETS)}')
    df = read_geojson_gzip(DATA_PATH / f'{dataset}.geojson.zip')
    df['dem_name'] = dataset
    df.crs = CRS.from_epsg(4326)
    return df


def get_overlapping_dem_tiles(bounds: list, dem_name: str) -> gpd.GeoDataFrame:
    """_summary_

    Parameters
    ----------
    bounds : list
        4326 bounds as xmin, ymin, xmax, ymax
    dem_name : str
        A DEM name supported e.g. 'glo_30', 'glo_90', 'nasadem'

    Returns
    -------
    gpd.GeoDataFrame
        Columns are `tile_id`, `url`, `geometry` and `dem_name`

    Raises
    ------
    DEMNotSupported
       If not in supported dem Name
    """
    check_4326_bounds(bounds)

    if dem_name not in DATASETS:
        raise DEMNotSupported(f'Please use dem_name in: {", ".join(DATASETS)}')
    box_geo = box(*bounds)
    df_tiles_all = get_global_dem_tile_extents(dem_name)

    crossing = get_dateline_crossing(bounds)
    if crossing:
        warn('Getting tiles across dateline on the opposite hemisphere; '
             f'The source tiles will be {- 2 * crossing} deg along the'
             'longitudinal axis from the extent requested',
             category=UserWarning)
        df_tiles_all_translated = df_tiles_all.copy()
        x_translation = 2 * crossing
        df_tiles_all_translated.geometry = df_tiles_all.geometry.translate(xoff=x_translation)
        df_tiles_all = pd.concat([df_tiles_all, df_tiles_all_translated], axis=0).reset_index(drop=True)

    overlap_index = df_tiles_all.intersects(box_geo)
    df_tiles = df_tiles_all[overlap_index].copy()

    # This removes de-generate instances when the bounds overlap is a Point or LineString
    # If empty, then additional intersection removes column names so addition this conditional flow
    # so subsequent sorting does not fail
    if not df_tiles.empty:
        df_tiles_intersection = df_tiles.geometry.intersection(box_geo)
        geo_type_index = df_tiles_intersection.geometry.map(lambda geo: geo.geom_type == 'Polygon')
        df_tiles = df_tiles[geo_type_index].copy()

    # Merging is order dependent - ensures consistency
    df_tiles = df_tiles.sort_values(by='tile_id')
    df_tiles = df_tiles.reset_index(drop=True)
    return df_tiles


def intersects_missing_glo_30_tiles(extent: list) -> bool:
    extent_geo = box(*extent)
    df_missing = get_overlapping_dem_tiles(extent, 'glo_90_missing')
    return df_missing.intersects(extent_geo).sum() > 0
