import shutil
import subprocess
from pathlib import Path
from typing import Callable, Union

import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_allclose, assert_almost_equal, assert_array_equal
from osgeo import gdal
from rasterio import default_gtiff_profile
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from shapely.geometry import box

from dem_stitcher import get_dem_tile_paths, stitch_dem
from dem_stitcher.datasets import DATASETS
from dem_stitcher.geoid import get_geoid_path, read_geoid
from dem_stitcher.rio_tools import reproject_arr_to_match_profile, translate_profile
from dem_stitcher.stitcher import merge_and_transform_dem_tiles, shift_profile_for_pixel_loc


"""
See: https://www.usgs.gov/special-topics/significant-topographic-changes-in-the-united-states/science/
srtm-ned-vertical?qt-science_center_objects=0#qt-science_center_objects

Simple test to check if translation is done correctly

All permutations of Area (or UL corner valued/gdal default) and Point (or pixel-centered, which is what SRTM uses)
"""

src_tags = ['Area', 'Area', 'Point', 'Point']

dst_tags = ['Area', 'Point', 'Point', 'Area']

t = Affine(1, 0, 10, 0, -1, 0)
transforms = [
    t,
    Affine(1, 0, 9.5, 0, -1, 0.5),
    t,
    Affine(1, 0, 10.5, 0, -1, -0.5),
]


@pytest.mark.parametrize('src_tag, dst_tag, transform_expected', zip(src_tags, dst_tags, transforms))
def test_shift_pixel_loc(src_tag: str, dst_tag: str, transform_expected: Affine) -> None:
    # Create dummy profile with reference transform
    p = default_gtiff_profile.copy()
    t_ref = Affine(1, 0, 10, 0, -1, 0)
    p['transform'] = t_ref

    # Translate if necessary
    p_new = shift_profile_for_pixel_loc(p, src_tag, dst_tag)
    t_new = p_new['transform']

    # Check the transform is what we expect
    assert transform_expected == t_new


@pytest.mark.parametrize('dem_name', ['glo_30', 'nasadem'])
def test_no_change_when_no_transformations_to_tile(
    get_los_angeles_tile_dataset: Callable[[str], rasterio.DatasetReader], dem_name: str
) -> None:
    """Open a single glo tile, selects bounds contained inside of it and makes sure no modifications are made."""
    datasets = [get_los_angeles_tile_dataset(dem_name)]
    X_tile = datasets[0].read(1)
    p_tile = datasets[0].profile

    # Within the Los Angeles tile
    bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = merge_and_transform_dem_tiles(
        datasets,
        bounds,
        dem_name=dem_name,
        # Do not modify tile
        dst_ellipsoidal_height=False,
        dst_area_or_point='Point',
    )

    datasets[0].close()

    X_sub_r, _ = reproject_arr_to_match_profile(X_sub, p_sub, p_tile, num_threads=5, resampling='nearest')
    X_sub_r = X_sub_r[0, ...]

    # The subset will have nan values so only compare areas with nan values
    # when reprojected into the original tile
    mask = np.isnan(X_sub_r)
    subset_data = X_sub_r[~mask]
    tile_data = X_tile[~mask]

    assert_array_equal(subset_data, tile_data)


def _make_memory_dem_dataset_4269() -> tuple[MemoryFile, rasterio.DatasetReader, list[float]]:
    profile = default_gtiff_profile.copy()
    profile.update(
        {
            'dtype': np.float32,
            'count': 1,
            'height': 64,
            'width': 64,
            'crs': CRS.from_epsg(4269),
            'transform': Affine(1.0 / 3600.0, 0, -120, 0, -(1.0 / 3600.0), 35),
            'nodata': np.nan,
        }
    )
    arr = np.arange(64 * 64, dtype=np.float32).reshape(64, 64)
    memfile = MemoryFile()
    dataset = memfile.open(**profile)
    dataset.write(arr[None, ...])
    dataset.update_tags(AREA_OR_POINT='Area')
    bounds = [-119.998, 34.985, -119.985, 34.998]
    return memfile, dataset, bounds


@pytest.mark.parametrize(
    'dst_resolution, expected_res_xy',
    [
        (0.0005, (0.0005, 0.0005)),
        ((0.0005, 0.00075), (0.0005, 0.00075)),
    ],
)
def test_output_profile_matches_requested_crs_and_resolution_for_4269_input(
    dst_resolution: Union[float, tuple[float, float]], expected_res_xy: tuple[float, float]
) -> None:
    memfile, dataset, bounds = _make_memory_dem_dataset_4269()
    try:
        dem_arr, dem_profile = merge_and_transform_dem_tiles(
            datasets=[dataset],
            bounds=bounds,
            dem_name='3dep',
            dst_ellipsoidal_height=False,
            dst_area_or_point='Area',
            dst_resolution=dst_resolution,
        )
    finally:
        dataset.close()
        memfile.close()

    assert dem_arr.shape[0] == 1
    assert dem_profile['crs'] == CRS.from_epsg(4326)
    assert dem_profile['transform'].a == expected_res_xy[0]
    assert abs(dem_profile['transform'].e) == expected_res_xy[1]


def test_4269_reprojection_branch_matches_rio_warp(tmp_path: Path) -> None:
    src_path = tmp_path / 'src_4269.tif'
    expected_path = tmp_path / 'expected_4326.tif'
    rio = shutil.which('rio')
    if rio is None:
        pytest.skip('rio CLI is required for this test')

    memfile, dataset, _ = _make_memory_dem_dataset_4269()
    try:
        with rasterio.open(src_path, 'w', **dataset.profile) as src_ds:
            src_ds.write(dataset.read())
            src_ds.update_tags(**dataset.tags())
    finally:
        dataset.close()
        memfile.close()

    subprocess.run(
        [
            rio,
            'warp',
            str(src_path),
            str(expected_path),
            '--dst-crs',
            'EPSG:4326',
            '--resampling',
            'bilinear',
            '--threads',
            '1',
            '--overwrite',
        ],
        check=True,
    )

    with rasterio.open(src_path) as src_ds:
        bounds = [
            src_ds.bounds.left,
            src_ds.bounds.bottom,
            src_ds.bounds.right,
            src_ds.bounds.top,
        ]
        dem_arr, dem_profile = merge_and_transform_dem_tiles(
            datasets=[src_ds],
            bounds=bounds,
            dem_name='3dep',
            dst_ellipsoidal_height=False,
            dst_area_or_point='Area',
            dst_resolution=None,
            num_threads_reproj=1,
            n_threads_for_reading_tile_data=1,
        )

    with rasterio.open(expected_path) as expected_ds:
        expected_arr = expected_ds.read()
        expected_profile = expected_ds.profile

    assert dem_profile['crs'] == expected_profile['crs']
    assert dem_profile['transform'] == expected_profile['transform']
    assert dem_profile['width'] == expected_profile['width']
    assert dem_profile['height'] == expected_profile['height']
    assert_allclose(dem_arr, expected_arr, equal_nan=True, atol=1e-6)


@pytest.mark.integration
@pytest.mark.parametrize('dem_name', DATASETS)
def test_download_dem(dem_name: str) -> None:
    if dem_name == 'glo_90_missing':
        # Missing area
        bounds = [45.5, 39.5, 46.5, 40.5]
    else:
        # Within the Los Angeles tile
        bounds = [-118.8, 34.6, -118.5, 34.8]

    dem_arr, p = stitch_dem(
        bounds, dem_name, n_threads_downloading=5, dst_ellipsoidal_height=True, dst_resolution=0.0002777777777777777775
    )
    assert len(dem_arr.shape) == 2
    assert np.isnan(p['nodata'])


def test_boundary_of_missing_glo_30_data() -> None:
    # See https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/89#issuecomment-1399142499
    bounds = [42.0, 37.0, 44.0, 39.0]
    dem_arr, p = stitch_dem(
        bounds, 'glo_30', n_threads_downloading=5, dst_ellipsoidal_height=True, dst_resolution=0.0002777777777777777775
    )
    assert len(dem_arr.shape) == 2
    assert np.isnan(p['nodata'])


@pytest.mark.integration
def test_mask_differences_with_merge_nodata_values_without_ellipsoidal() -> None:
    # Aleutian tiles follow chain so there is lots of nodata
    aleutian_bounds = [-167.5, 53.5, -164.5, 54.5]

    X_nan, p_nan = stitch_dem(
        aleutian_bounds,
        dem_name='glo_30',
        dst_ellipsoidal_height=False,
        dst_area_or_point='Point',
        merge_nodata_value=np.nan,
    )

    X_zero, p_zero = stitch_dem(
        aleutian_bounds,
        dem_name='glo_30',
        dst_ellipsoidal_height=False,
        dst_area_or_point='Point',
        merge_nodata_value=0,
    )

    assert X_zero.shape == X_nan.shape
    assert p_nan['transform'] == p_zero['transform']
    assert np.isnan(p_zero['nodata'])

    mask_nan = np.isnan(X_nan)
    mask_zero = X_zero == 0

    # There may be zeros within the tiles so we check a containment of masks
    # Checks if all elements in mask_zero are True where mask_nan
    assert (mask_zero[mask_nan]).all()
    assert_array_equal(X_zero[~mask_nan], X_nan[~mask_nan])


@pytest.mark.integration
def test_mask_differences_with_merge_nodata_values_with_ellipsoidal() -> None:
    """Check that when using merge_nodata_value it provides geoid values in missing data areas."""
    # Aleutian tiles follow chain so there is lots of nodata
    aleutian_bounds = [-167.5, 53.5, -164.5, 54.5]

    X_nan, p_nan = stitch_dem(
        aleutian_bounds,
        dem_name='glo_30',
        dst_ellipsoidal_height=True,
        dst_area_or_point='Point',
        merge_nodata_value=np.nan,
    )
    # Need to use nan mask to get all nodata areas with respect to tiles
    mask_nan = np.isnan(X_nan)

    X_zero, _ = stitch_dem(
        aleutian_bounds, dem_name='glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point', merge_nodata_value=0
    )

    geoid_path = get_geoid_path('egm_08')
    X_geoid, p_geoid = read_geoid(geoid_path, aleutian_bounds, res_buffer=5)
    p_geoid = translate_profile(p_geoid, -0.5, -0.5)

    X_geoid_r, _ = reproject_arr_to_match_profile(X_geoid, p_geoid, p_nan)
    X_geoid_r = X_geoid_r[0, ...]

    assert_almost_equal(X_zero[mask_nan], X_geoid_r[mask_nan], decimal=6)


def test_bad_merge_nodata_value() -> None:
    with pytest.raises(ValueError):
        stitch_dem([-118.8, 34.6, -118.5, 34.8], dem_name='glo_30', merge_nodata_value=3)


@pytest.mark.integration
def test_get_dem_tile_paths_and_output_vrt(test_dir: Path) -> None:
    input_bounds = [-121.5, 34.95, -120.2, 36.25]
    dem_name = 'glo_30'

    dem_tile_paths = get_dem_tile_paths(bounds=input_bounds, dem_name=dem_name, localize_tiles_to_gtiff=False)
    vrt_path = str(test_dir / f'test_{dem_name}.vrt')
    ds = gdal.BuildVRT(vrt_path, dem_tile_paths)
    del ds

    input_geo = box(*input_bounds)
    with rasterio.open(vrt_path) as ds_vrt:
        output_geo = box(*ds_vrt.bounds)

    assert output_geo.contains(input_geo)


@pytest.mark.parametrize('hgt_type', ['geoid', 'ellipsoid'])
@pytest.mark.parametrize('location', ['los_angeles', 'fairbanks'])
def test_against_golden_datasets(
    location: str,
    hgt_type: str,
    get_tile_paths_for_comparison_with_golden_dataset: Callable[[str], list[str]],
    get_golden_dataset_path: Callable[[str, str], str],
    get_geoid_for_golden_dataset_test: Callable[[str], tuple[np.ndarray, dict]],
    mocker: pytest.MonkeyPatch,
) -> None:
    if location == 'los_angeles':
        bounds = [-118.05, 33.95, -117.95, 34.05]
        dst_resolution = None
    if location == 'fairbanks':
        bounds = [-147.75, 64.75, -147.65, 64.85]
        dst_resolution = 0.0002777777

    mocker.patch(
        'dem_stitcher.stitcher.get_dem_tile_paths',
        side_effect=[get_tile_paths_for_comparison_with_golden_dataset(location)],
    )

    mocker.patch('dem_stitcher.geoid.read_geoid', side_effect=[get_geoid_for_golden_dataset_test(location)])

    path_golden = get_golden_dataset_path(location, hgt_type)

    with rasterio.open(path_golden) as ds:
        X_golden = ds.read(1)
        transform_golden = ds.transform

    X, p = stitch_dem(
        bounds,
        dem_name='glo_30',
        dst_ellipsoidal_height=(hgt_type == 'ellipsoid'),
        dst_area_or_point='Point',
        dst_resolution=dst_resolution,
    )
    assert_almost_equal(X_golden, X, decimal=7)
    assert transform_golden == p['transform']


@pytest.mark.parametrize('dem_name, geoid_name', [('3dep', 'geoid_18'), ('glo_30', 'egm_08')])
def test_stitcher_with_bring_your_own_geoid(dem_name: str, geoid_name: str) -> None:
    bounds = [-115.95, 33.85, -115.85, 33.95]
    geoid_path = get_geoid_path(geoid_name)
    X_explicit, p_explicit = stitch_dem(
        bounds,
        dem_name=dem_name,
        dst_ellipsoidal_height=True,
        dst_area_or_point='Point',
        dst_resolution=None,
        geoid_path=geoid_path,
    )

    X_default, p_default = stitch_dem(
        bounds,
        dem_name=dem_name,
        dst_ellipsoidal_height=True,
        dst_area_or_point='Point',
        dst_resolution=None,
        geoid_path=None,
    )

    assert_allclose(X_explicit, X_default)
    assert p_default == p_explicit


def test_error_with_bring_your_own_geoid_without_ellipsoidal_height() -> None:
    bounds = [-115.95, 33.85, -115.85, 33.95]
    with pytest.raises(ValueError, match='Cannot bring your own geoid when dst_ellipsoidal_height is False'):
        stitch_dem(bounds, dem_name='glo_30', dst_ellipsoidal_height=False, dst_area_or_point='Point', geoid_path='foo')

    with pytest.raises(FileNotFoundError, match='Geoid file foo does not exist.'):
        stitch_dem(bounds, dem_name='glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point', geoid_path='foo')
