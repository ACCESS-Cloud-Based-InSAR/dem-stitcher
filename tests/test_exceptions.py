import pytest

from dem_stitcher import stitch_dem
from dem_stitcher.exceptions import DEMNotSupported, Incorrect4326Bounds, NoDEMCoverage


def test_dem_not_supported() -> None:
    with pytest.raises(DEMNotSupported):
        bounds = [-120, 34, -119, 35]

        stitch_dem(bounds, dem_name='dem-not-supported')


def test_no_coverage() -> None:
    with pytest.raises(NoDEMCoverage):
        # Middle of the Atlantic
        bounds = [-46, 22, -45, 23]
        stitch_dem(bounds, dem_name='glo_30')


def test_bad_extents() -> None:
    with pytest.raises(Incorrect4326Bounds):
        bounds = [-119, 34, -120, 35]
        stitch_dem(bounds, dem_name='glo_30')
