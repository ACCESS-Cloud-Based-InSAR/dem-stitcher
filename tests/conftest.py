from pathlib import Path

import pytest
import rasterio


@pytest.fixture(scope='session')
def test_data_dir():
    data_dir = Path(__file__).resolve().parent / 'data'
    return data_dir


@pytest.fixture
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
