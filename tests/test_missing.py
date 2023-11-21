import pytest
import rasterio
from numpy.testing import assert_almost_equal

from dem_stitcher import stitch_dem
from dem_stitcher.merge import merge_arrays_with_geometadata
from dem_stitcher.stitcher import intersects_missing_glo_30_tiles

extents = [
           # On boundary of missing tiles (both glo-90, glo-30)
           [42.95, 40.45, 43.05, 40.55],
           # Contained within missing tiles
           [43.95, 40.45, 44.05, 40.55],
           # Outside
           [41.95, 40.45, 42.05, 40.55],
           ]

containment = [True, True, False]


def _open_one(path):
    with rasterio.open(path) as ds:
        X = ds.read(1)
        p = ds.profile
    return X, p


@pytest.mark.parametrize('extent, containment', zip(extents, containment))
def test_intersects_missing_tiles(extent, containment):
    assert intersects_missing_glo_30_tiles(extent) == containment


def test_merge_glo30_and_glo_90(test_data_dir):
    data_dir = test_data_dir / 'missing'
    glo_30_left_path = data_dir / 'glo_30_left.tif'
    glo_90_right_path = data_dir / 'glo_90_right.tif'
    glo_merged_path = data_dir / 'glo_merged.tif'

    X_glo_30, p_glo_30 = _open_one(glo_30_left_path)
    X_glo_90, p_glo_90 = _open_one(glo_90_right_path)
    X_merged, p_merged = _open_one(glo_merged_path)

    X_merged_out, p_merged_out = merge_arrays_with_geometadata([X_glo_30, X_glo_90],
                                                               [p_glo_30, p_glo_90])

    assert_almost_equal(X_merged, X_merged_out[0, ...], decimal=6)
    assert p_merged_out['transform'] == p_merged['transform']


@pytest.mark.integration
def test_glo_90_filling(test_data_dir):

    data_dir = test_data_dir / 'missing'
    glo_merged_path = data_dir / 'glo_merged.tif'

    # Parameters for stitching
    dst_area_or_point = 'Point'
    dst_ellipsoidal_height = False
    dem_name = 'glo_30'

    bounds = [42.95, 40.45, 43.05, 40.55]

    X_filled, p_filled = stitch_dem(bounds,
                                    dem_name=dem_name,
                                    dst_ellipsoidal_height=dst_ellipsoidal_height,
                                    dst_area_or_point=dst_area_or_point,
                                    fill_in_glo_30=True)

    X_merged, p_merged = _open_one(glo_merged_path)

    assert_almost_equal(X_merged, X_filled, decimal=6)
    assert p_filled['transform'] == p_merged['transform']
