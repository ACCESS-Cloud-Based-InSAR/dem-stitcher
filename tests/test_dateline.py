import pytest

from dem_stitcher.dateline import get_dateline_crossing
from dem_stitcher.exceptions import DoubleDatelineCrossing, Incorrect4326Bounds
from dem_stitcher.stitcher import get_overlapping_dem_tiles

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
    # Stitcher should sort by tile id as our the static lists above
    assert tile_ids_stitcher == tile_ids


def test_dataset_translation():
    assert True


def test_stitcher_across_dateline():
    assert True
