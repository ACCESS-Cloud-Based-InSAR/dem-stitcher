import pytest

from dem_stitcher.dateline import get_dateline_crossing, split_extent_across_dateline
from dem_stitcher.exceptions import DoubleDatelineCrossing, Incorrect4326Bounds
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
               ]
exceptions = [DoubleDatelineCrossing, Incorrect4326Bounds, Incorrect4326Bounds]


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


bounds_list = [[-181, 51, -179, 52],
               # [179, 51, 181, 52]
               ]


@pytest.mark.integration
@pytest.mark.parametrize("bounds", bounds_list)
def test_stithcer_across_dateline(bounds):
    X, p = stitch_dem(bounds, 'glo_30', dst_ellipsoidal_height=True)
    assert len(X.shape) == 2
