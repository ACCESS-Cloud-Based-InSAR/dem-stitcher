from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_allclose, assert_almost_equal, assert_array_equal
from osgeo import gdal
from rasterio import default_gtiff_profile
from shapely.geometry import box

from dem_stitcher import get_dem_tile_paths, stitch_dem
from dem_stitcher.datasets import DATASETS, get_global_dem_tile_extents
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


def test_area_and_point_outputs_have_identical_samples(
    get_los_angeles_tile_dataset: Callable[[str], rasterio.DatasetReader],
) -> None:
    """Check `dst_area_or_point` only relabels the transform by half a pixel; the samples are identical.

    The geoid is removed on the native grid (i.e. sampled where the DEM samples physically are) before the
    relabeling, so both outputs carry identical ellipsoidal heights;
    see https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/151.
    """
    bounds = [-118.8, 34.6, -118.5, 34.8]
    geoid_path = get_geoid_path('geoid_18')

    results = {}
    for tag in ['Point', 'Area']:
        datasets = [get_los_angeles_tile_dataset('glo_30')]
        results[tag] = merge_and_transform_dem_tiles(
            datasets,
            bounds,
            dem_name='glo_30',
            dst_ellipsoidal_height=True,
            dst_area_or_point=tag,
            geoid_path=geoid_path,
        )
        datasets[0].close()

    X_point, p_point = results['Point']
    X_area, p_area = results['Area']

    assert_array_equal(X_point, X_area)
    assert p_area['transform'] == translate_profile(p_point, 0.5, 0.5)['transform']


def test_dst_area_or_point_none_inherits_source_registration(
    get_los_angeles_tile_dataset: Callable[[str], rasterio.DatasetReader],
) -> None:
    """The default `dst_area_or_point=None` keeps the source registration ('Point' for glo_30 tiles)."""
    bounds = [-118.8, 34.6, -118.5, 34.8]

    results = {}
    for tag in [None, 'Point']:
        datasets = [get_los_angeles_tile_dataset('glo_30')]
        results[tag] = merge_and_transform_dem_tiles(
            datasets,
            bounds,
            dem_name='glo_30',
            dst_ellipsoidal_height=False,
            dst_area_or_point=tag,
        )
        datasets[0].close()

    X_inherited, p_inherited = results[None]
    X_point, p_point = results['Point']

    assert p_inherited['transform'] == p_point['transform']
    assert_array_equal(X_inherited, X_point)


def test_bad_dst_area_or_point() -> None:
    with pytest.raises(ValueError, match="dst_area_or_point must be 'Area', 'Point', or None"):
        stitch_dem([-118.8, 34.6, -118.5, 34.8], dem_name='glo_30', dst_area_or_point='foo')


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

    X_geoid_r, _ = reproject_arr_to_match_profile(X_geoid, p_geoid, p_nan, resampling='cubic')
    X_geoid_r = X_geoid_r[0, ...]

    assert_allclose(X_zero[mask_nan], X_geoid_r[mask_nan], rtol=1e-6, atol=1e-6)


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


@pytest.mark.integration
def test_glo_30_agrees_with_nisar_dem_over_random_tiles() -> None:
    """Check stitched glo_30 with ellipsoidal heights against the NISAR DEM over randomly selected tiles.

    The NISAR DEM is the Copernicus GLO-30 with EGM2008 removed at the source by JPL on the native tile grids,
    so both stitches must share a transform and agree to within the geoid interpolation differences (~mm);
    guards against the half-pixel geoid translation of issue #151, which produced cm-dm level discrepancies.
    """
    df_tiles = get_global_dem_tile_extents('glo_30')
    df_sample = df_tiles.sample(3, random_state=151)

    for geometry in df_sample.geometry:
        centroid = geometry.centroid
        bounds = [centroid.x - 0.05, centroid.y - 0.05, centroid.x + 0.05, centroid.y + 0.05]

        X_nisar, p_nisar = stitch_dem(bounds, 'nisar_dem', dst_area_or_point='Point')
        X_glo, p_glo = stitch_dem(bounds, 'glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point')

        assert p_nisar['transform'] == p_glo['transform']
        mask = ~np.isnan(X_nisar) & ~np.isnan(X_glo)
        assert mask.any()
        assert np.max(np.abs(X_nisar[mask] - X_glo[mask])) < 0.01


def test_nisar_dem_is_ellipsoidal_only() -> None:
    bounds = [-118.8, 34.6, -118.5, 34.8]
    with pytest.raises(ValueError, match='geoid heights are not available'):
        stitch_dem(bounds, dem_name='nisar_dem', dst_ellipsoidal_height=False)

    with pytest.raises(ValueError, match='a geoid cannot be removed'):
        stitch_dem(bounds, dem_name='nisar_dem', geoid_path=get_geoid_path('egm_08'))


def test_error_with_bring_your_own_geoid_without_ellipsoidal_height() -> None:
    bounds = [-115.95, 33.85, -115.85, 33.95]
    with pytest.raises(ValueError, match='Cannot bring your own geoid when dst_ellipsoidal_height is False'):
        stitch_dem(bounds, dem_name='glo_30', dst_ellipsoidal_height=False, dst_area_or_point='Point', geoid_path='foo')

    with pytest.raises(FileNotFoundError, match='Geoid file foo does not exist.'):
        stitch_dem(bounds, dem_name='glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point', geoid_path='foo')
