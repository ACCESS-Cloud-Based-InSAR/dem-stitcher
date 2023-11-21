from pathlib import Path

import pytest
import rasterio
from affine import Affine
from rasterio import default_gtiff_profile
from rasterio.crs import CRS


@pytest.fixture(scope='session')
def test_dir():
    test_dir = Path(__file__).resolve().parent
    return test_dir


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
            NotImplementedError(f'Not implemented for {dem_name}')
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


@pytest.fixture(scope='session')
def get_tile_paths_for_comparison_with_golden_dataset():
    golden_dataset_dir = Path(__file__).resolve().parent / 'data' / 'golden_datasets'

    def _get_tile_dataset(location: str) -> list:
        if location not in ['fairbanks', 'los_angeles']:
            raise NotImplementedError
        dem_tile_dir = golden_dataset_dir / f'{location}_tiles'
        paths = list(dem_tile_dir.glob('*.tif'))
        paths_str = list(map(str, paths))
        paths_str = sorted(paths_str)
        return paths_str

    return _get_tile_dataset


@pytest.fixture(scope='session')
def get_golden_dataset_path():
    golden_dataset_dir = Path(__file__).resolve().parent / 'data' / 'golden_datasets'

    def _get_golden_dataset_path(location: str, hgt_type: str) -> str:
        if location not in ['fairbanks', 'los_angeles']:
            raise NotImplementedError
        return str(golden_dataset_dir / f'{location}_dem_{hgt_type}.tif')

    return _get_golden_dataset_path


@pytest.fixture(scope='session')
def get_geoid_for_golden_dataset_test():
    golden_dataset_dir = Path(__file__).resolve().parent / 'data' / 'golden_datasets'

    def _get_geoid(location: str) -> str:
        if location not in ['fairbanks', 'los_angeles']:
            raise NotImplementedError
        geoid_path = golden_dataset_dir / f'egm_08_{location}.tif'
        with rasterio.open(geoid_path) as ds:
            X = ds.read(1)
            p = ds.profile
        return X, p

    return _get_geoid
