import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Tuple, Union

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.merge import merge
from shapely.geometry import box
from tqdm import tqdm

from .datasets import DATASETS, get_dem_tile_extents
from .dem_readers import read_dem, read_nasadem, read_ned1, read_srtm
from .exceptions import DEMNotSupported, NoDEMCoverage
from .geoid import remove_geoid
from .glo_30_missing import merge_glo_30_and_90_dems
from .rio_tools import (reproject_arr_to_match_profile,
                        reproject_arr_to_new_crs, translate_profile,
                        update_profile_resolution)
from .rio_window import get_indices_from_extent

RASTER_READERS = {'ned1': read_ned1,
                  '3dep': read_dem,
                  'glo_30': read_dem,
                  'glo_90': read_dem,
                  'glo_90_missing': read_dem,
                  'srtm_v3': read_srtm,
                  'nasadem': read_nasadem}

DEM2GEOID = {'ned1': 'geoid_18',
             '3dep': 'geoid_18',
             'glo_30': 'egm_08',
             'glo_90': 'egm_08',
             'glo_90_missing': 'egm_08',
             'srtm_v3': 'egm_96',
             'nasadem': 'egm_96'}

PIXEL_CENTER_DEMS = ['srtm_v3', 'nasadem', 'glo_30', 'glo_90', 'glo_90_missing']


def get_dem_tiles(bounds: list, dem_name: str) -> gpd.GeoDataFrame:
    if dem_name not in DATASETS:
        raise DEMNotSupported(f'Please use dem_name in: {", ".join(DATASETS)}')
    box_sh = box(*bounds)
    df_tiles_all = get_dem_tile_extents(dem_name)
    index = df_tiles_all.intersects(box_sh)
    df_tiles = df_tiles_all[index].copy()

    # Merging is order dependent - ensures consistency
    df_tiles.sort_values(by='tile_id')
    df_tiles = df_tiles.reset_index(drop=True)
    return df_tiles


def intersects_missing_glo_30_tiles(extent: list) -> bool:
    extent_geo = box(*extent)
    df_missing = get_dem_tiles(extent, 'glo_90_missing')
    return df_missing.intersects(extent_geo).sum() > 0


def _download_and_write_one_tile(url: str,
                                 dest_path: Path,
                                 reader: Callable,
                                 dem_name: str) -> dict:
    dem_arr, dem_profile = reader(url)
    # if dem_arr is None - the tile does not exist - this is the case
    # for glo30
    if dem_arr is None:
        return

    dem_profile['driver'] = 'GTiff'
    with rasterio.open(dest_path, 'w', **dem_profile) as ds:
        ds.write(dem_arr, 1)
        if dem_name in PIXEL_CENTER_DEMS:
            ds.update_tags(AREA_OR_POINT='Point')
    return dem_profile


def download_tiles(urls: list,
                   dem_name: str,
                   dest_dir: Path,
                   max_workers: int = 5
                   ) -> List[Path]:

    tile_ids = list(map(lambda x: x.split('/')[-1], urls))
    dest_paths = list(map(lambda tile_id: dest_dir/f'{tile_id}.tif',
                          tile_ids))
    reader = RASTER_READERS[dem_name]

    def download_and_write_one_partial(zipped_data: list) -> dict:
        return _download_and_write_one_tile(zipped_data[0],
                                            zipped_data[1],
                                            reader,
                                            dem_name)

    data_list = zip(urls, dest_paths)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(tqdm(executor.map(download_and_write_one_partial, data_list),
                            total=len(urls),
                            desc=f'Downloading {dem_name} tiles'))
    profiles = results

    n = len(dest_paths)
    dest_paths_f = [dest_paths[k] for k in range(n) if profiles[k] is not None]

    return dest_paths_f


def merge_tiles(datasets: List[rasterio.DatasetReader],
                bounds: list = None,
                resampling: str = 'nearest',
                res_buffer: int = 0
                ) -> Tuple[np.ndarray, dict]:
    merged_arr, merged_transform = merge(datasets,
                                         resampling=Resampling[resampling],
                                         # This fixes the nodata values
                                         nodata=np.nan,
                                         # This fixes the float32 output
                                         dtype='float32',
                                         )
    merged_arr = merged_arr[0, ...]

    # each pair is in (row, col) format
    corner_ul, corner_br = get_indices_from_extent(merged_transform,
                                                   bounds,
                                                   shape=merged_arr.shape,
                                                   res_buffer=res_buffer)
    sy = np.s_[corner_ul[0]: corner_br[0]]
    sx = np.s_[corner_ul[1]: corner_br[1]]
    merged_arr = merged_arr[sy, sx]

    # We swap row and columns because Affine expects (x, y) or (col, row)
    origin_affine = corner_ul[1], corner_ul[0]
    new_origin = merged_transform * origin_affine
    merged_transform_final = Affine.translation(*new_origin)
    merged_transform_final = merged_transform_final * Affine.scale(merged_transform.a,
                                                                   merged_transform.e)

    profile = datasets[0].profile.copy()
    profile['height'] = merged_arr.shape[0]
    profile['width'] = merged_arr.shape[1]
    profile['nodata'] = np.nan
    profile['dtype'] = 'float32'
    profile['transform'] = merged_transform_final
    return merged_arr, profile


def shift_profile_for_pixel_loc(src_profile: dict,
                                src_area_or_point: str,
                                dst_area_or_point: str) -> dict:
    assert(dst_area_or_point in ['Area', 'Point'])
    assert(src_area_or_point in ['Area', 'Point'])
    if dst_area_or_point == 'Point' and src_area_or_point == 'Area':
        shift = -.5
        profile_shifted = translate_profile(src_profile, shift, shift)
    elif (dst_area_or_point == 'Area') and (src_area_or_point == 'Point'):
        shift = .5
        profile_shifted = translate_profile(src_profile, shift, shift)
    else:
        profile_shifted = src_profile.copy()
    return profile_shifted


def merge_and_transform_dem_tiles(datasets: list,
                                  bounds: list,
                                  dem_name: str,
                                  dst_ellipsoidal_height: bool = True,
                                  dst_area_or_point: str = 'Area',
                                  dst_resolution: Union[float, Tuple[float]] = None,
                                  num_threads_reproj: int = 5) -> Tuple[np.ndarray, dict]:
    dem_arr, dem_profile = merge_tiles(datasets,
                                       bounds=bounds)
    src_area_or_point = datasets[0].tags().get('AREA_OR_POINT', 'Area')

    dem_profile = shift_profile_for_pixel_loc(dem_profile,
                                              src_area_or_point,
                                              dst_area_or_point)

    # Reproject to 4326 for USGS DEMs over North America
    # Note 4269 is almost identical to 4326 and often no changes are made
    if dem_profile['crs'] == CRS.from_epsg(4269):
        dem_arr, dem_profile = reproject_arr_to_new_crs(dem_arr,
                                                        dem_profile,
                                                        CRS.from_epsg(4326))
        dem_arr = dem_arr[0, ...]

    if dem_profile['crs'] != CRS.from_epsg(4326):
        raise ValueError('CRS must be epsg 4269 or 4326')

    if dst_ellipsoidal_height:
        geoid_name = DEM2GEOID[dem_name]
        dem_arr = remove_geoid(dem_arr,
                               dem_profile,
                               geoid_name,
                               dem_area_or_point=dst_area_or_point,
                               )

    if dst_resolution is not None:
        dem_profile_res = update_profile_resolution(dem_profile, dst_resolution)
        dem_arr, dem_profile = reproject_arr_to_match_profile(dem_arr,
                                                              dem_profile,
                                                              dem_profile_res,
                                                              num_threads=num_threads_reproj,
                                                              resampling='bilinear')
        dem_arr = dem_arr[0, ...]

    # Ensure dem_arr has correct shape
    assert(len(dem_arr.shape) == 2)

    return dem_arr, dem_profile


def patch_glo_30_with_glo_90(arr_glo_30: np.ndarray,
                             prof_glo_30: dict,
                             extent: list,
                             stitcher_kwargs: dict) -> Tuple[np.ndarray, dict]:
    if not intersects_missing_glo_30_tiles(extent):
        return arr_glo_30, prof_glo_30

    stitcher_kwargs['dem_name'] = 'glo_90_missing'
    arr_glo_90, prof_glo_90 = stitch_dem(**stitcher_kwargs)

    dem_arr, dem_prof = merge_glo_30_and_90_dems(arr_glo_30,
                                                 prof_glo_30,
                                                 arr_glo_90,
                                                 prof_glo_90
                                                 )

    return dem_arr, dem_prof


def stitch_dem(bounds: list,
               dem_name: str,
               dst_ellipsoidal_height: bool = True,
               dst_area_or_point: str = 'Area',
               dst_resolution: Union[float, Tuple[float]] = None,
               n_threads_reproj: int = 5,
               n_threads_downloading=5,
               driver: str = 'GTiff',
               fill_in_glo_30: bool = True
               ) -> Tuple[np.ndarray, dict]:
    """This is API for stitching DEMs

    Parameters
    ----------
    bounds : list
        [xmin, ymin, xmax, ymax] in epsg:4326 (i.e. x=lon and y=lat)
    dem_name : str
        One of the dems supported by the stitcher (use `from dem_stitcher.datasets import DATASETS; DATASETS`)
    dst_ellipsoidal_height : bool, optional
        If True, removes the geoid. If not, then they are in the reference geoid height. By default True
    dst_area_or_point : str, optional
        Can be 'Area' or 'Point'. The former means each pixel is referenced with respect to the upper
        left corner. The latter means the pixel is center at its own center. By default 'Area' (as is `gdal`)
    dst_resolution : Union[float, Tuple[float]], optional
        Can be float (square pixel with float resolution) or (x_res, y_res). When None is specified,
        then the DEM tile resolution is used. By default None
    n_threads_reproj : int, optional
        Threads to use for reprojection, by default 5
    n_threads_downloading : int, optional
        Threads for downloading tiles, by default 5
    driver : str, optional
        Output format in profile, by default 'GTiff'
    fill_in_glo_30 : bool, optional
        If `dem_name` is 'glo_30' then fills in missing `glo_30` tiles over Armenia and Azerbaijan with available
        `glo_90` tiles, by default True. If the extent falls inside of the missing `glo_30` tiles, then `glo_90` is
        upsample to 30 meters unless `dst_resolution` is specified.

    Returns
    -------
    Tuple[np.ndarray, dict]
        (DEM Array, metadata dictionary). The metadata dictionary can be used as in rasterio to write the array
        in a gdal compatible format. See the
        [notebooks](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/tree/dev/notebooks)
        for demonstrations.
    """
    # Used for filling in glo_30 missing tiles if needed
    stitcher_kwargs = locals()

    if dem_name not in DATASETS:
        raise DEMNotSupported(f'Please use dem_name in: {", ".join(DATASETS)}')

    if (bounds[0] > bounds[2]) or (bounds[1] > bounds[3]):
        raise ValueError('Specify bounds as xmin, ymin, xmax, ymax in epsg:4326')

    df_tiles = get_dem_tiles(bounds, dem_name)
    urls = df_tiles.url.tolist()

    # Random unique identifier
    tmp_id = str(uuid.uuid4())
    tile_dir = Path(f'tmp_{tmp_id}')

    # Datasets that permit virtual warping
    # The readers return DatasetReader rather than (Array, Profile)
    if dem_name in ['glo_30', 'glo_90', '3dep', 'glo_90_missing']:
        def reader(url):
            return RASTER_READERS[dem_name](url)
        with ThreadPoolExecutor(max_workers=n_threads_downloading) as executor:
            results = list(tqdm(executor.map(reader, urls),
                                total=len(urls),
                                desc=f'Reading {dem_name} Datasets'))

        # If datasets are non-existent, returns None
        datasets = list(filter(lambda x: x is not None, results))
    else:
        tile_dir.mkdir(exist_ok=True, parents=True)
        dest_paths = download_tiles(urls,
                                    dem_name,
                                    tile_dir,
                                    max_workers=n_threads_downloading)
        datasets = list(map(rasterio.open, dest_paths))

    if not datasets:
        # This is the case that an extent is entirely contained within glo_90
        if ((dem_name == 'glo_30') and fill_in_glo_30 and intersects_missing_glo_30_tiles(bounds)):

            stitcher_kwargs['dem_name'] = 'glo_90_missing'
            # if dst_resolution is None, then make sure we upsample to 30 meter resolution
            dst_resolution = stitcher_kwargs['dst_resolution']
            stitcher_kwargs['dst_resolution'] = dst_resolution or 0.0002777777777777777775

            dem_arr, dem_profile = stitch_dem(**stitcher_kwargs)
            return dem_arr, dem_profile
        else:
            raise NoDEMCoverage(f'Specified bounds are not within coverage area of {dem_name}')

    dem_arr, dem_profile = merge_and_transform_dem_tiles(datasets,
                                                         bounds,
                                                         dem_name,
                                                         dst_ellipsoidal_height=dst_ellipsoidal_height,
                                                         dst_area_or_point=dst_area_or_point,
                                                         dst_resolution=dst_resolution,
                                                         num_threads_reproj=n_threads_reproj,
                                                         )

    # Close datasets
    list(map(lambda dataset: dataset.close(), datasets))

    # Delete orginal tiles if downloaded
    if tile_dir.exists():
        shutil.rmtree(str(tile_dir))

    # Set driver in profile
    dem_profile['driver'] = driver

    if (dem_name == 'glo_30') and fill_in_glo_30:
        dem_arr, dem_profile = patch_glo_30_with_glo_90(dem_arr,
                                                        dem_profile,
                                                        bounds,
                                                        stitcher_kwargs)

    return dem_arr, dem_profile
