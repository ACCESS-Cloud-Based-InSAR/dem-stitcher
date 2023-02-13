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
