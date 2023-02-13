import pytest
from numpy.testing import assert_almost_equal

from dem_stitcher.dateline import (get_dateline_crossing,
                                   split_extent_across_dateline)
from dem_stitcher.exceptions import DoubleDatelineCrossing, Incorrect4326Bounds
from dem_stitcher.geoid import read_geoid
from dem_stitcher.merge import merge_arrays_with_geometadata
from dem_stitcher.rio_tools import translate_profile
from dem_stitcher.stitcher import get_overlapping_dem_tiles, stitch_dem

bounds_list = [[179, 52, 181, 53],
               [179.1, -13, 180.001, -12.1],
               [-181, 33, -179, 34.5],
               [-180.1, -89, -178.8, -88],
               [100, 0, 101, 1],
               [-33, 10, -32, 12]
               ]
crossings = [180, 180, -180, -180, 0, 0]


@pytest.mark.parametrize("bounds, crossing", zip(bounds_list, crossings))
def test_dateline_crossing(bounds, crossing):
    assert get_dateline_crossing(bounds) == crossing


bounds_list = [[-181, 0, 181, 1],
               [-200, 0, -181, 1],
               [180.01, 0, 200, 1],
               [52, 89, 53, 91],
               [52, -91, 53, -89],
               ]
exceptions = [DoubleDatelineCrossing,
              Incorrect4326Bounds,
              Incorrect4326Bounds,
              Incorrect4326Bounds,
              Incorrect4326Bounds]


@pytest.mark.parametrize("bounds, exception", zip(bounds_list, exceptions))
def test_dateline_exceptions(bounds, exception):
    with pytest.raises(exception):
        get_dateline_crossing(bounds)


bounds_list = [[-180.25, 51.25, -179.75, 51.75],
               [179.75, 51.25, 180.25, 51.75]]
tiles_ids_list = [['Copernicus_DSM_COG_10_N51_00_E179_00_DEM', 'Copernicus_DSM_COG_10_N51_00_W180_00_DEM'],
                  ['Copernicus_DSM_COG_10_N51_00_E179_00_DEM', 'Copernicus_DSM_COG_10_N51_00_W180_00_DEM']]


@pytest.mark.parametrize("bounds, tile_ids", zip(bounds_list, tiles_ids_list))
def test_get_tiles_across_dateline(bounds, tile_ids):
    df_tiles_overlapping = get_overlapping_dem_tiles(bounds, 'glo_30')
    tile_ids_stitcher = df_tiles_overlapping.tile_id.tolist()
    # Stitcher should sort by tile id as is the case with the static tile lists above are
    assert tile_ids_stitcher == tile_ids


bounds_list = [[-181, 51, -179, 52],
               [-171, 51, -169, 52]]

outputs = [([-180.0, 51.0, -179.0, 52.0], [179.0, 51.0, 180.0, 52.0]),
           ([-171, 51, -169, 52], [])]


@pytest.mark.parametrize("bounds, split_extent_known", zip(bounds_list, outputs))
def test_split_extent(bounds, split_extent_known):
    split_extent_output = split_extent_across_dateline(bounds)
    assert split_extent_output == split_extent_known


bounds_list = [[-181, 51.25, -179, 51.75],
               [179, 51, 181, 52]
               ]


@pytest.mark.integration
@pytest.mark.parametrize("bounds", bounds_list)
def test_stithcer_across_dateline(bounds):
    X, _ = stitch_dem(bounds, 'glo_30', dst_ellipsoidal_height=True)
    assert len(X.shape) == 2


@pytest.mark.integration
def test_stitcher_across_dateline_approaching_from_left_and_right():
    bounds_l = [-181, 51.25, -179, 51.75]
    X_l, p_l = stitch_dem(bounds_l, 'glo_30', dst_ellipsoidal_height=False, dst_area_or_point='Point')

    bounds_r = [179, 51.25, 181, 51.75]
    X_r, p_r = stitch_dem(bounds_r, 'glo_30', dst_ellipsoidal_height=False, dst_area_or_point='Point')

    # Metadata should be the same after translation
    res_x = p_r['transform'].a
    p_r_t = translate_profile(p_r, -360 / res_x, 0)

    # Georefernencing
    assert p_r_t['crs'] == p_l['crs']
    assert p_r_t['transform'] == p_l['transform']

    # Arrays should be the same as well
    assert_almost_equal(X_r, X_l, 5)


@pytest.mark.integration
def test_read_geoid_across_dateline():
    bounds = [-181, 51.25, -179, 51.75]
    geoid_arr_dateline, p = read_geoid('egm_08', bounds, res_buffer=1)

    bounds_l = [-179.999, 51.25, -179, 51.75]
    geoid_arr_l, p_l = read_geoid('egm_08', bounds_l, res_buffer=1)

    bounds_r = [179, 51.25, 179.999, 51.75]
    geoid_arr_r, p_r = read_geoid('egm_08', bounds_r, res_buffer=1)

    res_x = p_r['transform'].a
    p_r_t = translate_profile(p_r, -360 / res_x, 0)

    geoid_merged, _ = merge_arrays_with_geometadata([geoid_arr_l, geoid_arr_r],
                                                    [p_l, p_r_t])

    assert_almost_equal(geoid_merged, geoid_arr_dateline, 5)
