from pathlib import Path

import pytest
import rasterio
from affine import Affine
from rasterio import default_gtiff_profile
from rasterio.crs import CRS


@pytest.fixture(scope='session')
def test_data_dir():
    data_dir = Path(__file__).resolve().parent / 'data'
    return data_dir


@pytest.fixture(scope='session')
def notebooks_dir():
    notebook_directory = Path(__file__).resolve().parents[1] / 'notebooks'
    return notebook_directory


@pytest.fixture(scope='session')
def get_los_angeles_tile_dataset():
    tiles_dir = Path(__file__).resolve().parent / 'data' / 'tiles'

    def _get_tile_dataset(dem_name):
        dem_tile_dir = tiles_dir / f'{dem_name}'
        if dem_name == 'glo_30':
            tile_name = 'Copernicus_DSM_COG_10_N34_00_W119_00_DEM.tif'
        elif dem_name == 'nasadem':
            tile_name = 'NASADEM_HGT_n34w119.tif'
        else:
            ValueError(f'Not implemented for {dem_name}')
        tile_path = dem_tile_dir / tile_name
        return rasterio.open(tile_path)

    return _get_tile_dataset


@pytest.fixture(scope='session')
def get_los_angeles_dummy_profile():

    def _get_dummy_profile(res: float):
        p_la = default_gtiff_profile.copy()
        t = Affine(res, 0, -118, 0, -res, 35)
        p_la['transform'] = t
        p_la['width'] = 10
        p_la['height'] = 10
        p_la['count'] = 1
        p_la['crs'] = CRS.from_epsg(4326)
        return p_la

    return _get_dummy_profile
