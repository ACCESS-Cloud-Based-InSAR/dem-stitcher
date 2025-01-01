import warnings
from typing import Callable

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from dem_stitcher.geoid import get_geoid_path, read_geoid, remove_geoid
from dem_stitcher.rio_tools import reproject_arr_to_match_profile


"""We will test 'geoid_18' over US because we include that in package datasets, i.e. no internet reading is required"""


def test_read_geoid() -> None:
    # entire geoid
    geoid_path = get_geoid_path('geoid_18')
    X_all, p_all = read_geoid(geoid_path)

    # Over Los Angeles
    la_bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = read_geoid(geoid_path, extent=la_bounds, res_buffer=1)

    X_sub_r, p_r = reproject_arr_to_match_profile(X_sub, p_sub, p_all)

    mask = np.isnan(X_sub_r)
    data_sub = X_sub_r[~mask]
    data_all = X_all[~mask]

    assert_array_equal(data_sub, data_all)
    assert p_r['transform'] == p_all['transform']


@pytest.mark.parametrize('dem_res', [0.001, 0.01, 0.1, 1])
def test_remove_geoid(get_los_angeles_dummy_profile: Callable[[float], dict], dem_res: float) -> None:
    """
    Test removing a geoid against a zero array.

    Expected: should bereprojected into the DEM reference frame. If the DEM resolution >> geoid resolution, then
    we must select a buffer to read the geoid such that it covers the extended boundary DEM pixel completely.
    If not, then the resampling around the boundary will be different in this test because we only read a subset
    of the geoid array.
    """
    p_ref = get_los_angeles_dummy_profile(res=dem_res)
    geoid_path = get_geoid_path('geoid_18')
    X_geoid, p_geoid = read_geoid(geoid_path)

    res_buffer_default = 2

    X_sub, _ = reproject_arr_to_match_profile(X_geoid, p_geoid, p_ref)

    Y = np.zeros((10, 10), dtype=np.float32)
    if dem_res >= 0.1:
        geoid_res = p_geoid['transform'].a
        with pytest.warns(UserWarning):
            _ = remove_geoid(Y, p_ref, geoid_path)

        res_buffer_updated = int(np.ceil(dem_res / geoid_res))
        assert res_buffer_default < res_buffer_updated

        X_sub_2 = remove_geoid(Y, p_ref, geoid_path, res_buffer=res_buffer_updated)

    else:
        X_sub_2 = remove_geoid(Y, p_ref, geoid_path, res_buffer=res_buffer_default)

    assert_array_equal(X_sub_2, X_sub)


def test_warning_with_geoid_not_covering_dateline() -> None:
    geoid_path_not_covering_dateline = 'https://aria-geoid.s3.us-west-2.amazonaws.com/egm08_25.tif'
    with pytest.warns(UserWarning, match='Geoid file does not cover the dateline'):
        extent = [-181, -78.176201, -177.884048, -75.697151]
        _, _ = read_geoid(geoid_path_not_covering_dateline, extent=extent)

    geoid_path_covering_dateline = 'https://aria-geoid.s3.us-west-2.amazonaws.com/us_nga_egm2008_1_4326__agisoft.tif'
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter('always')
        _, _ = read_geoid(geoid_path_covering_dateline, extent=extent)

        for warning in caught_warnings:
            assert 'Geoid file does not cover the dateline. May have np.nan' not in str(warning.message)
