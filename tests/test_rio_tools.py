import rasterio
from numpy.testing import assert_almost_equal

from dem_stitcher.rio_tools import (reproject_arr_to_match_profile,
                                    update_profile_resolution)


def test_update_resolution(test_data_dir):
    """Checks that reprojection to higher resolution via bilinear interpolation preservers geotransform and correctly
    resamples
    """

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
    assert res_quarter_deg == (.25, .25)

    p_higher_res = update_profile_resolution(p_one_deg, .25)
    X_quarter_deg_reprj, _ = reproject_arr_to_match_profile(X_one_deg,
                                                            p_one_deg,
                                                            p_higher_res,
                                                            resampling='bilinear')
    X_quarter_deg_reprj = X_quarter_deg_reprj[0, ...]

    assert_almost_equal(X_quarter_deg_reprj, X_quarter_deg, 5)
    assert t_quarter_deg == p_higher_res['transform']
