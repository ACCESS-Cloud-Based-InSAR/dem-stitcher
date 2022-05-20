import numpy as np
import pytest
from dem_stitcher.geoid import read_geoid, remove_geoid
from dem_stitcher.rio_tools import reproject_arr_to_match_profile
from numpy.testing import assert_array_equal

"""We will test 'geoid_18' over US because we include that in datasets so no interconnectivity required"""


def test_read_geoid():
    # entire geoid
    X_all, p_all = read_geoid('geoid_18')

    # Over Los Angeles
    la_bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = read_geoid('geoid_18', extent=la_bounds, res_buffer=1)

    X_sub_r, p_r = reproject_arr_to_match_profile(X_sub, p_sub, p_all)
    X_sub_r = X_sub_r[0, ...]

    mask = np.isnan(X_sub_r)
    data_sub = X_sub_r[~mask]
    data_all = X_all[~mask]

    assert_array_equal(data_sub, data_all)
    assert(p_r['transform'] == p_all['transform'])


@pytest.mark.parametrize("res", [.01, .1, 1])
def test_remove_geoid(get_los_angeles_dummy_profile, res):
    p_ref = get_los_angeles_dummy_profile(res=.1)
    X_geoid, p_geoid = read_geoid('geoid_18')

    X_sub, p_sub = reproject_arr_to_match_profile(X_geoid, p_geoid, p_ref)
    X_sub = X_sub[0, ...]

    Y = np.zeros((10, 10), dtype=np.float32)
    X_sub_2 = remove_geoid(Y, p_ref, 'geoid_18')

    assert_array_equal(X_sub_2, X_sub)
