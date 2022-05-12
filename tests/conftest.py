from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def test_data_dir():
    data_dir = Path(__file__).resolve().parent / 'data'
    return data_dir


@pytest.fixture(scope='session')
def los_angeles_glo30_path():
    glo_30_path = Path(__file__).resolve().parent / 'data' / 'tiles' / 'glo_30'
    la_path = glo_30_path / 'Copernicus_DSM_COG_10_N34_00_W119_00_DEM.tif'
    return la_path
