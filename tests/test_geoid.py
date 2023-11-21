import numpy as np
import pytest
from numpy.testing import assert_array_equal

from dem_stitcher.geoid import read_geoid, remove_geoid
from dem_stitcher.rio_tools import reproject_arr_to_match_profile


"""We will test 'geoid_18' over US because we include that in package datasets, i.e. no internet reading is required"""


def test_read_geoid():
    # entire geoid
    X_all, p_all = read_geoid('geoid_18')

    # Over Los Angeles
    la_bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = read_geoid('geoid_18', extent=la_bounds, res_buffer=1)

    X_sub_r, p_r = reproject_arr_to_match_profile(X_sub, p_sub, p_all)

    mask = np.isnan(X_sub_r)
    data_sub = X_sub_r[~mask]
    data_all = X_all[~mask]

    assert_array_equal(data_sub, data_all)
    assert p_r['transform'] == p_all['transform']


@pytest.mark.parametrize("dem_res", [.001, .01, .1, 1])
def test_remove_geoid(get_los_angeles_dummy_profile, dem_res):
    """
    We test removing a geoid against a zero array, which should literally be the entire geoid array
    reprojected into the DEM reference frame. If the DEM resolution >> geoid resolution, then
    we must select a buffer to read the geoid such that it covers the extended boundary DEM pixel completely.
    If not, then the resampling around the boundary will be different in this test because we only read a subset
    of the geoid array.
    """
    p_ref = get_los_angeles_dummy_profile(res=dem_res)
    X_geoid, p_geoid = read_geoid('geoid_18')

    res_buffer_default = 2

    X_sub, _ = reproject_arr_to_match_profile(X_geoid, p_geoid, p_ref)

    Y = np.zeros((10, 10), dtype=np.float32)
    if dem_res >= .1:
        geoid_res = p_geoid['transform'].a
        with pytest.warns(UserWarning):
            _ = remove_geoid(Y, p_ref, 'geoid_18')

        res_buffer_updated = (int(np.ceil(dem_res / geoid_res)))
        assert res_buffer_default < res_buffer_updated

        X_sub_2 = remove_geoid(Y, p_ref, 'geoid_18', res_buffer=res_buffer_updated)

    else:
        X_sub_2 = remove_geoid(Y, p_ref, 'geoid_18', res_buffer=res_buffer_default)

    assert_array_equal(X_sub_2, X_sub)
