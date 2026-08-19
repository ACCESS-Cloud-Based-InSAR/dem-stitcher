import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_allclose, assert_array_equal
from osgeo import gdal
from rasterio import default_gtiff_profile
from rasterio.crs import CRS
from rasterio.io import MemoryFile
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
    dst_resolution: float | tuple[float, float], expected_res_xy: tuple[float, float]
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


def test_legacy_mode_point_and_area_samples_differ(
    get_los_angeles_tile_dataset: Callable[[str], rasterio.DatasetReader],
) -> None:
    """Check `geoid_correction_mode='aria-legacy'` reproduces the pre-3.0.0 Point/Area discrepancy.

    Under the legacy correction the geoid grid is translated by half a *geoid* pixel for 'Point'
    (issue #151), so unlike the native mode the Point and Area samples differ.
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
            geoid_correction_mode='aria-legacy',
        )
        datasets[0].close()

    X_point, p_point = results['Point']
    X_area, p_area = results['Area']

    assert not np.array_equal(X_point, X_area, equal_nan=True)
    assert p_area['transform'] == translate_profile(p_point, 0.5, 0.5)['transform']


def test_bad_dst_area_or_point() -> None:
    with pytest.raises(ValueError, match="dst_area_or_point must be 'Area', 'Point', or None"):
        stitch_dem([-118.8, 34.6, -118.5, 34.8], dem_name='glo_30', dst_area_or_point='foo')


def test_bad_geoid_correction_mode() -> None:
    with pytest.raises(ValueError, match="geoid_correction_mode must be 'native' or 'aria-legacy'"):
        stitch_dem([-118.8, 34.6, -118.5, 34.8], dem_name='glo_30', geoid_correction_mode='foo')


def test_aria_legacy_invalid_combinations() -> None:
    bounds = [-118.8, 34.6, -118.5, 34.8]
    with pytest.raises(ValueError, match='requires dst_ellipsoidal_height=True'):
        stitch_dem(bounds, dem_name='glo_30', dst_ellipsoidal_height=False, geoid_correction_mode='aria-legacy')
    with pytest.raises(ValueError, match='referenced to the ellipsoid; no geoid correction'):
        stitch_dem(bounds, dem_name='nisar_dem', geoid_correction_mode='aria-legacy')


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
    # The golden GeoTIFFs are float32, so a single ULP at DEM magnitudes (~150 m) is already ~1.5e-5.
    # GDAL/numpy builds across the CI matrix differ by an ULP on isolated pixels; compare at 0.1 mm instead.
    assert_allclose(X_golden, X, rtol=1e-6, atol=1e-4)
    assert transform_golden == p['transform']


@pytest.mark.parametrize('location', ['los_angeles', 'fairbanks'])
def test_against_legacy_golden_datasets(
    location: str,
    get_tile_paths_for_comparison_with_golden_dataset: Callable[[str], list[str]],
    get_golden_dataset_path: Callable[[str, str], str],
    get_geoid_for_golden_dataset_test: Callable[[str], tuple[np.ndarray, dict]],
    mocker: pytest.MonkeyPatch,
) -> None:
    """Check `geoid_correction_mode='aria-legacy'` against goldens generated with `dem-stitcher==2.5.13`.

    The `*_dem_ellipsoid_legacy.tif` goldens were produced by running pip-installed 2.5.13 with the same
    cached tile crops and geoid crop mocked in below (see generate-datasets.ipynb), so this pins parity with
    the pre-3.0.0 geoid correction independent of live-tile drift. Verified bit-for-bit on the generating
    machine; asserted at 0.1 mm here for the same cross-CI ULP reason as `test_against_golden_datasets`.
    """
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

    path_golden = get_golden_dataset_path(location, 'ellipsoid_legacy')

    with rasterio.open(path_golden) as ds:
        X_golden = ds.read(1)
        transform_golden = ds.transform

    with pytest.warns(UserWarning, match='aria-legacy'):
        X, p = stitch_dem(
            bounds,
            dem_name='glo_30',
            dst_ellipsoidal_height=True,
            dst_area_or_point='Point',
            dst_resolution=dst_resolution,
            geoid_correction_mode='aria-legacy',
        )
    assert_allclose(X_golden, X, rtol=1e-6, atol=1e-4)
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


"""Copernicus coarsens the GLO-30 longitudinal posting to 1.5, 2, 3, 5 and 10 arcseconds at 50, 60, 70, 80 and 85
degrees latitude while the latitudinal posting stays at 1 arcsecond. The geoid shift of issue #151 is half a DEM
pixel, so it is anisotropic in these bands - sample a tile from each so a regression cannot hide above 50 degrees.
"""
GLO_30_POSTING_BANDS = [(0, 50), (50, 60), (60, 70), (70, 80), (80, 85)]


def _sample_glo_30_tile_center(lat_min: float, lat_max: float) -> tuple[float, float]:
    df_tiles = get_global_dem_tile_extents('glo_30')
    tile_bounds = df_tiles.geometry.bounds
    lat = tile_bounds[['miny', 'maxy']].abs().min(axis=1)
    df_band = df_tiles[(lat >= lat_min) & (lat < lat_max)]
    b = df_band.sample(1, random_state=151).geometry.bounds.iloc[0]
    return (b.minx + b.maxx) / 2, (b.miny + b.maxy) / 2


@pytest.mark.integration
@pytest.mark.parametrize('lat_min, lat_max', GLO_30_POSTING_BANDS)
def test_glo_30_agrees_with_nisar_dem_over_random_tiles(lat_min: float, lat_max: float) -> None:
    """Check stitched glo_30 with ellipsoidal heights against the NISAR DEM over a randomly selected tile per band.

    The NISAR DEM is the Copernicus GLO-30 with EGM2008 removed at the source by JPL on the native tile grids,
    so both stitches must share a grid and agree to within the geoid interpolation differences (~mm);
    guards against the half-pixel geoid translation of issue #151, which produced cm-dm level discrepancies.
    """
    x, y = _sample_glo_30_tile_center(lat_min, lat_max)
    bounds = [x - 0.05, y - 0.05, x + 0.05, y + 0.05]

    X_nisar, p_nisar = stitch_dem(bounds, 'nisar_dem', dst_area_or_point='Point')
    X_glo, p_glo = stitch_dem(bounds, 'glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point')

    # The 1.5 and 3 arcsecond postings round to floats that differ by a ULP between the NISAR and Copernicus headers
    assert p_nisar['transform'].almost_equals(p_glo['transform'])
    assert X_nisar.shape == X_glo.shape
    mask = ~np.isnan(X_nisar) & ~np.isnan(X_glo)
    assert mask.any()
    assert np.max(np.abs(X_nisar[mask] - X_glo[mask])) < 0.01


@pytest.mark.integration
def test_glo_30_agrees_with_nisar_dem_over_anchorage() -> None:
    """Anchorage sits in the 2 arcsecond longitudinal posting band; the notebook comparison uses these bounds."""
    bounds = [-150.0, 61.15, -149.9, 61.25]

    X_nisar, p_nisar = stitch_dem(bounds, 'nisar_dem', dst_area_or_point='Point')
    X_glo, p_glo = stitch_dem(bounds, 'glo_30', dst_ellipsoidal_height=True, dst_area_or_point='Point')

    assert p_glo['transform'].a == pytest.approx(2 / 3600)
    assert -p_glo['transform'].e == pytest.approx(1 / 3600)
    assert p_nisar['transform'].almost_equals(p_glo['transform'])
    assert np.nanmax(np.abs(X_nisar - X_glo)) < 0.01


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
