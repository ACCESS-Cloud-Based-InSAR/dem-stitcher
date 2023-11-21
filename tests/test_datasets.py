import warnings

import pytest

from dem_stitcher.datasets import get_overlapping_dem_tiles

extents = [
           # This is overlapping with Points/LineString for missing tiles
           # See https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/89#issuecomment-1399142499
           [40.0, 36.0, 44.0, 40.0],
           # Middle of Atlantic
           [-46, 22, -45, 23]
          ]
dem_names = ['glo_90_missing', 'glo_30']


@pytest.mark.parametrize('extent, dem_name', zip(extents, dem_names))
def test_empty_tiles(extent, dem_name):
    df_tiles = get_overlapping_dem_tiles(extent, dem_name)
    assert df_tiles.empty


def test_dateline_warning():
    extent_no_dateline = [-121.5, 34.95, -120.2, 36.25]
    with warnings.catch_warnings():
        warnings.simplefilter("error", category=UserWarning)
        get_overlapping_dem_tiles(extent_no_dateline, 'glo_30')

    extent_with_dateline = [-181, 51.25, -179, 51.75]
    with pytest.warns(UserWarning):
        get_overlapping_dem_tiles(extent_with_dateline, 'glo_30')
