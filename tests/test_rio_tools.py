from pathlib import Path

import numpy as np
import pytest
import rasterio
from numpy.testing import assert_almost_equal
from rasterio.crs import CRS

from dem_stitcher.credentials import earthdata_gdal_env
from dem_stitcher.dem_readers import read_dem
from dem_stitcher.rio_tools import (
    gdal_read_env,
    reproject_arr_to_match_profile,
    reproject_arr_to_new_crs,
    translate_dataset,
    update_profile_resolution,
    with_gdal_read_env,
)
from dem_stitcher.rio_window import get_array_bounds, read_raster_from_window


def test_update_resolution(test_data_dir: Path) -> None:
    """Check that reprojection to higher resolution via bilinear interpolation preservers geotransform correctly."""
    data_dir = test_data_dir / 'rio_tools' / 'update_resolution'
    assert data_dir.exists()

    with rasterio.open(data_dir / 'res_one_deg.tif') as ds:
        p_one_deg = ds.profile
        X_one_deg = ds.read(1)
        res_one_deg = ds.res

    with rasterio.open(data_dir / 'res_quarter_deg.tif') as ds:
        p_quarter_deg = ds.profile
        X_quarter_deg = ds.read(1)
        res_quarter_deg = ds.res

    t_one_deg = p_one_deg['transform']
    t_quarter_deg = p_quarter_deg['transform']
    assert (t_one_deg * (0, 0)) == (t_quarter_deg * (0, 0))
    assert res_one_deg == (1, 1)
    assert res_quarter_deg == (0.25, 0.25)

    p_higher_res = update_profile_resolution(p_one_deg, 0.25)
    X_quarter_deg_reprj, _ = reproject_arr_to_match_profile(X_one_deg, p_one_deg, p_higher_res, resampling='bilinear')
    X_quarter_deg_reprj = X_quarter_deg_reprj[0, ...]

    assert_almost_equal(X_quarter_deg_reprj, X_quarter_deg, 5)
    assert t_quarter_deg == p_higher_res['transform']
    assert X_quarter_deg_reprj.dtype == np.float32


def test_dataset_translation(test_data_dir: Path) -> None:
    data_dir = test_data_dir / 'dateline' / 'translate_datasets'

    assert data_dir.exists()

    ds_left = rasterio.open(data_dir / 'left.tif')
    ds_right = rasterio.open(data_dir / 'right.tif')

    res_x = ds_left.res[0]
    mfile, ds_left_t = translate_dataset(ds_left, 360 / res_x, 0)

    assert ds_left_t.transform == ds_right.transform
    assert_almost_equal(ds_left_t.read(), ds_right.read(), 5)

    ds_left_t.close()
    ds_right.close()
    mfile.close()


def test_reproject_preserve_rank(test_data_dir: Path) -> None:
    """preserve_rank=True returns 2D for 2D input; default and 3D behavior are unchanged."""
    data_dir = test_data_dir / 'rio_tools' / 'update_resolution'
    with rasterio.open(data_dir / 'res_one_deg.tif') as ds:
        p_src = ds.profile
        X_2d = ds.read(1)
        X_3d = ds.read()

    p_ref = update_profile_resolution(p_src, 0.25)

    X_r_2d, p_r_2d = reproject_arr_to_match_profile(X_2d, p_src, p_ref, preserve_rank=True)
    assert X_r_2d.shape == (p_ref['height'], p_ref['width'])
    assert p_r_2d['count'] == 1

    X_r_3d, _ = reproject_arr_to_match_profile(X_3d, p_src, p_ref, preserve_rank=True)
    assert X_r_3d.shape == (1, p_ref['height'], p_ref['width'])

    X_r_default, _ = reproject_arr_to_match_profile(X_2d, p_src, p_ref)
    assert X_r_default.shape == (1, p_ref['height'], p_ref['width'])
    assert_almost_equal(X_r_default[0, ...], X_r_2d, 7)

    utm_crs = CRS.from_epsg(32632)
    X_c_2d, p_c_2d = reproject_arr_to_new_crs(X_2d, p_src, utm_crs, preserve_rank=True)
    assert X_c_2d.ndim == 2
    assert p_c_2d['count'] == 1

    X_c_3d, _ = reproject_arr_to_new_crs(X_3d, p_src, utm_crs, preserve_rank=True)
    assert X_c_3d.ndim == 3

    X_c_default, _ = reproject_arr_to_new_crs(X_2d, p_src, utm_crs)
    assert X_c_default.ndim == 3
    assert_almost_equal(X_c_default[0, ...], X_c_2d, 7)


@pytest.mark.parametrize('bad_shape', [(10,), (1, 1, 10, 10)])
def test_reproject_raises_on_bad_rank(test_data_dir: Path, bad_shape: tuple) -> None:
    data_dir = test_data_dir / 'rio_tools' / 'update_resolution'
    with rasterio.open(data_dir / 'res_one_deg.tif') as ds:
        p_src = ds.profile

    X_bad = np.zeros(bad_shape, dtype=np.float32)
    with pytest.raises(ValueError, match='2 or 3 dimensional'):
        reproject_arr_to_match_profile(X_bad, p_src, p_src)
    with pytest.raises(ValueError, match='2 or 3 dimensional'):
        reproject_arr_to_new_crs(X_bad, p_src, CRS.from_epsg(32632))


def test_reproject_to_new_crs_preserves_dtype(test_data_dir: Path) -> None:
    """reproject_arr_to_new_crs should return an array matching the source dtype."""
    data_dir = test_data_dir / 'rio_tools' / 'update_resolution'
    with rasterio.open(data_dir / 'res_one_deg.tif') as ds:
        src_profile = ds.profile
        src_arr = ds.read()

    assert src_profile['dtype'] == 'float32'

    # UTM zone 32N covers the test tile's location (lon 10-12, lat -2 to 0)
    result_arr, _ = reproject_arr_to_new_crs(src_arr, src_profile, CRS.from_epsg(32632), resampling='bilinear')
    assert result_arr.dtype == np.float32


def test_gdal_read_env_disables_sidecar_probing() -> None:
    """Sidecar probes on remote rasters are 403s that GDAL logs as warnings; see issue DockerizedTopsApp#262."""

    @with_gdal_read_env
    def get_option() -> str:
        return rasterio.env.getenv()['GDAL_DISABLE_READDIR_ON_OPEN']

    assert get_option() == 'EMPTY_DIR'
    for env in [gdal_read_env(), earthdata_gdal_env()]:
        assert env.options['GDAL_DISABLE_READDIR_ON_OPEN'] == 'EMPTY_DIR'
    # An outer environment (e.g. the Earthdata options) is preserved by the nested read environment
    with earthdata_gdal_env():
        assert get_option() == 'EMPTY_DIR'
        assert rasterio.env.getenv()['GDAL_HTTP_NETRC'] == 'YES'


def test_read_functions_run_within_gdal_read_env(test_data_dir: Path) -> None:
    tile_path = test_data_dir / 'rio_tools' / 'update_resolution' / 'res_one_deg.tif'
    _, profile = read_dem(str(tile_path))
    assert profile['width'] > 0

    extent = list(get_array_bounds(profile))
    arr_window, _ = read_raster_from_window(str(tile_path), extent)
    assert arr_window.shape[-2:] == (profile['height'], profile['width'])
