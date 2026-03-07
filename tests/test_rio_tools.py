from pathlib import Path

import numpy as np
import rasterio
from numpy.testing import assert_almost_equal
from rasterio.crs import CRS

from dem_stitcher.rio_tools import (
    reproject_arr_to_match_profile,
    reproject_arr_to_new_crs,
    translate_dataset,
    update_profile_resolution,
)


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


def test_reproject_to_new_crs_preserves_dtype(test_data_dir: Path) -> None:
    """reproject_arr_to_new_crs should return an array matching the source dtype."""
    data_dir = test_data_dir / 'rio_tools' / 'update_resolution'
    with rasterio.open(data_dir / 'res_one_deg.tif') as ds:
        src_profile = ds.profile
        src_arr = ds.read()

    assert src_profile['dtype'] == 'float32'

    # UTM zone 32N covers the test tile's location (lon 10-12, lat -2 to 0)
    result_arr, _ = reproject_arr_to_new_crs(
        src_arr, src_profile, CRS.from_epsg(32632), resampling='bilinear'
    )
    assert result_arr.dtype == np.float32
