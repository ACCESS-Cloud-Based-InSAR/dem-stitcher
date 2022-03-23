import pytest

from dem_stitcher import stitch_dem
from dem_stitcher.datasets import DATASETS


@pytest.mark.parametrize("dem_name", DATASETS)
def test_download_dem(tmp_path, dem_name):
    dem_file = tmp_path / f'{dem_name}_full_res.dem.wgs84'

    # Bay Area
    bounds = [-121.5, 34.95, -120.2, 36.25]
    stitch_dem(bounds,
               dem_name,
               filepath=str(dem_file),
               max_workers=5,
               dst_ellipsoidal_height=False
               )

    assert dem_file.exists()
