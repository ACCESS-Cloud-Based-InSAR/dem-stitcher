import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_almost_equal, assert_array_equal
from osgeo import gdal
from rasterio import default_gtiff_profile
from shapely.geometry import box

from dem_stitcher import get_dem_tile_paths, stitch_dem
from dem_stitcher.datasets import DATASETS
from dem_stitcher.geoid import read_geoid
from dem_stitcher.rio_tools import (reproject_arr_to_match_profile,
                                    translate_profile)
from dem_stitcher.stitcher import (merge_and_transform_dem_tiles,
                                   shift_profile_for_pixel_loc)


"""
See: https://www.usgs.gov/special-topics/significant-topographic-changes-in-the-united-states/science/srtm-ned-vertical?qt-science_center_objects=0#qt-science_center_objects  # noqa: E501

Simple test to check if translation is done correctly

All permutations of Area (or UL corner valued/gdal default) and Point (or pixel-centered, which is what SRTM uses)
"""

src_tags = ['Area',
            'Area',
            'Point',
            'Point'
            ]

dst_tags = ['Area',
            'Point',
            'Point',
            'Area'
            ]

t = Affine(1, 0, 10, 0, -1, 0)
transforms = [
              t,
              Affine(1, 0, 9.5, 0, -1, 0.5),
              t,
              Affine(1, 0, 10.5, 0, -1, -0.5),
              ]


@pytest.mark.parametrize("src_tag, dst_tag, transform_expected", zip(src_tags, dst_tags, transforms))
def test_shift_pixel_loc(src_tag, dst_tag, transform_expected):

    # Create dummy profile with reference transform
    p = default_gtiff_profile.copy()
    t_ref = Affine(1, 0, 10, 0, -1, 0)
    p['transform'] = t_ref

    # Translate if necessary
    p_new = shift_profile_for_pixel_loc(p, src_tag, dst_tag)
    t_new = p_new['transform']

    # Check the transform is what we expect
    assert transform_expected == t_new


@pytest.mark.parametrize("dem_name", ['glo_30', 'nasadem'])
def test_no_change_when_no_transformations_to_tile(get_los_angeles_tile_dataset, dem_name):
    """Opens a single glo tile, selects bounds contained inside of it and then reprojects the obtained tile back into
    the tiles original frame to determine if modifications were made.
    """
    datasets = [get_los_angeles_tile_dataset(dem_name)]
    X_tile = datasets[0].read(1)
    p_tile = datasets[0].profile

    # Within the Los Angeles tile
    bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = merge_and_transform_dem_tiles(datasets,
                                                 bounds,
                                                 dem_name=dem_name,
                                                 # Do not modify tile
                                                 dst_ellipsoidal_height=False,
                                                 dst_area_or_point='Point')

    datasets[0].close()

    X_sub_r, _ = reproject_arr_to_match_profile(X_sub, p_sub, p_tile,
                                                num_threads=5,
                                                resampling='nearest')
    X_sub_r = X_sub_r[0, ...]

    # The subset will have nan values so only compare areas with nan values
    # when reprojected into the original tile
    mask = np.isnan(X_sub_r)
    subset_data = X_sub_r[~mask]
    tile_data = X_tile[~mask]

    assert_array_equal(subset_data, tile_data)


@pytest.mark.integration
@pytest.mark.parametrize("dem_name", DATASETS)
def test_download_dem(dem_name):
    if dem_name == 'glo_90_missing':
        # Missing area
        bounds = [45.5, 39.5, 46.5, 40.5]
    else:
        # Within the Los Angeles tile
        bounds = [-118.8, 34.6, -118.5, 34.8]

    dem_arr, p = stitch_dem(bounds,
                            dem_name,
                            n_threads_downloading=5,
                            dst_ellipsoidal_height=True,
                            dst_resolution=0.0002777777777777777775
                            )
    assert len(dem_arr.shape) == 2
    assert np.isnan(p['nodata'])


def test_boundary_of_missing_glo_30_data():
    # See https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/89#issuecomment-1399142499
    bounds = [42.0, 37.0, 44.0, 39.0]
    dem_arr, p = stitch_dem(bounds,
                            'glo_30',
                            n_threads_downloading=5,
                            dst_ellipsoidal_height=True,
                            dst_resolution=0.0002777777777777777775
                            )
    assert len(dem_arr.shape) == 2
    assert np.isnan(p['nodata'])


@pytest.mark.integration
def test_mask_differences_with_merge_nodata_values_without_ellipsoidal():
    # Aleutian tiles follow chain so there is lots of nodata
    aleutian_bounds = [-167.5, 53.5, -164.5, 54.5]

    X_nan, p_nan = stitch_dem(aleutian_bounds,
                              dem_name='glo_30',
                              dst_ellipsoidal_height=False,
                              dst_area_or_point='Point',
                              merge_nodata_value=np.nan)

    X_zero, p_zero = stitch_dem(aleutian_bounds,
                                dem_name='glo_30',
                                dst_ellipsoidal_height=False,
                                dst_area_or_point='Point',
                                merge_nodata_value=0)

    assert X_zero.shape == X_nan.shape
    assert p_nan['transform'] == p_zero['transform']
    assert np.isnan(p_zero['nodata'])

    mask_nan = np.isnan(X_nan)
    mask_zero = (X_zero == 0)

    # There may be zeros within the tiles so we check a containment of masks
    # Checks if all elements in mask_zero are True where mask_nan
    assert (mask_zero[mask_nan]).all()
    assert_array_equal(X_zero[~mask_nan], X_nan[~mask_nan])


@pytest.mark.integration
def test_mask_differences_with_merge_nodata_values_with_ellipsoidal():
    """Checks that when using merge_nodata_value it
    provides geoid values in missing data areas
    """
    # Aleutian tiles follow chain so there is lots of nodata
    aleutian_bounds = [-167.5, 53.5, -164.5, 54.5]

    X_nan, p_nan = stitch_dem(aleutian_bounds,
                              dem_name='glo_30',
                              dst_ellipsoidal_height=True,
                              dst_area_or_point='Point',
                              merge_nodata_value=np.nan)
    # Need to use nan mask to get all nodata areas with respect to tiles
    mask_nan = np.isnan(X_nan)

    X_zero, _ = stitch_dem(aleutian_bounds,
                           dem_name='glo_30',
                           dst_ellipsoidal_height=True,
                           dst_area_or_point='Point',
                           merge_nodata_value=0)

    X_geoid, p_geoid = read_geoid('egm_08', aleutian_bounds, res_buffer=5)
    p_geoid = translate_profile(p_geoid, -.5, -.5)

    X_geoid_r, _ = reproject_arr_to_match_profile(X_geoid, p_geoid, p_nan)
    X_geoid_r = X_geoid_r[0, ...]

    assert_almost_equal(X_zero[mask_nan], X_geoid_r[mask_nan], decimal=6)


def test_bad_merge_nodata_value():
    with pytest.raises(ValueError):
        stitch_dem([-118.8, 34.6, -118.5, 34.8],
                   dem_name='glo_30',
                   merge_nodata_value=3)


@pytest.mark.integration
def test_get_dem_tile_paths_and_output_vrt(test_dir):
    input_bounds = [-121.5, 34.95, -120.2, 36.25]
    dem_name = 'glo_30'

    dem_tile_paths = get_dem_tile_paths(bounds=input_bounds,
                                        dem_name=dem_name,
                                        localize_tiles_to_gtiff=False
                                        )
    vrt_path = str(test_dir / f'test_{dem_name}.vrt')
    ds = gdal.BuildVRT(vrt_path, dem_tile_paths)
    ds = None

    input_geo = box(*input_bounds)
    with rasterio.open(vrt_path) as ds:
        output_geo = box(*ds.bounds)

    assert output_geo.contains(input_geo)


@pytest.mark.parametrize("hgt_type", ['geoid', 'ellipsoid'])
@pytest.mark.parametrize("location", ['los_angeles', 'fairbanks'])
def test_against_golden_datasets(location: str,
                                 hgt_type: str,
                                 get_tile_paths_for_comparison_with_golden_dataset,
                                 get_golden_dataset_path,
                                 get_geoid_for_golden_dataset_test,
                                 mocker):
    if location == 'los_angeles':
        bounds = [-118.05, 33.95, -117.95, 34.05]
        dst_resolution = None
    if location == 'fairbanks':
        bounds = [-147.75, 64.75, -147.65, 64.85]
        dst_resolution = .0002777777

    mocker.patch('dem_stitcher.stitcher.get_dem_tile_paths',
                 side_effect=[get_tile_paths_for_comparison_with_golden_dataset(location)])

    mocker.patch('dem_stitcher.geoid.read_geoid',
                 side_effect=[get_geoid_for_golden_dataset_test(location)])

    path_golden = get_golden_dataset_path(location, hgt_type)

    with rasterio.open(path_golden) as ds:
        X_golden = ds.read(1)
        transform_golden = ds.transform

    X, p = stitch_dem(bounds,
                      dem_name='glo_30',
                      dst_ellipsoidal_height=(hgt_type == 'ellipsoid'),
                      dst_area_or_point='Point',
                      dst_resolution=dst_resolution
                      )
    assert_almost_equal(X_golden, X, decimal=7)
    assert transform_golden == p['transform']
