from pathlib import Path
import geopandas as gpd
from rasterio.crs import CRS
from .geojson_io import read_geojson_gzip


DATA_PATH = Path(__file__).parents[0].absolute()/'data'

# Get Datasets
_DATASET_PATHS = list(DATA_PATH.glob('*.geojson.zip'))
DATASETS = list(map(lambda x: x.name.split('.')[0], _DATASET_PATHS))


def get_available_datasets():
    return DATASETS


def get_dem_tile_extents(dataset: str) -> gpd.GeoDataFrame:
    if dataset not in DATASETS:
        raise ValueError(f'{dataset} must be in {", ".join(DATASETS)}')
    df = read_geojson_gzip(DATA_PATH/f'{dataset}.geojson.zip')
    df['dem_name'] = dataset
    df.crs = CRS.from_epsg(4326)
    return df
