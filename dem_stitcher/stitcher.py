import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Union
from warnings import warn

import numpy as np
import rasterio
from rasterio import default_gtiff_profile
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from tqdm import tqdm

from .datasets import (get_overlapping_dem_tiles,
                       intersects_missing_glo_30_tiles)
from .dateline import get_dateline_crossing
from .dem_readers import read_dem, read_nasadem, read_srtm
from .exceptions import NoDEMCoverage
from .geoid import remove_geoid
from .merge import merge_arrays_with_geometadata, merge_tile_datasets_within_extent
from .rio_tools import (reproject_arr_to_match_profile,
                        reproject_arr_to_new_crs, translate_dataset,
                        translate_profile, update_profile_resolution)

RASTER_READERS = {'3dep': read_dem,
                  'glo_30': read_dem,
                  'glo_90': read_dem,
                  'glo_90_missing': read_dem,
                  'srtm_v3': read_srtm,
                  'nasadem': read_nasadem}

DEM2GEOID = {'3dep': 'geoid_18',
             'glo_30': 'egm_08',
             'glo_90': 'egm_08',
             'glo_90_missing': 'egm_08',
             'srtm_v3': 'egm_96',
             'nasadem': 'egm_96'}

PIXEL_CENTER_DEMS = ['srtm_v3', 'nasadem', 'glo_30', 'glo_90', 'glo_90_missing']
DEFAULT_GTIFF_PROFILE = default_gtiff_profile.copy()
DEFAULT_GTIFF_PROFILE.pop('nodata')
DEFAULT_GTIFF_PROFILE.pop('dtype')


def _download_and_write_one_tile_to_gtiff(url: str,
                                          dest_path: Path,
                                          reader: Callable,
                                          dem_name: str) -> dict:
    dem_arr, dem_profile = reader(url)
    if dem_profile['driver'] != 'GTiff':
        dem_profile.update(**DEFAULT_GTIFF_PROFILE)
    with rasterio.open(dest_path, 'w', **dem_profile) as ds:
        ds.write(dem_arr)
        if dem_name in PIXEL_CENTER_DEMS:
            ds.update_tags(AREA_OR_POINT='Point')
    return dem_profile


def download_tiles_to_gtiff(urls: list,
                            dem_name: str,
                            dest_dir: Path,
                            max_workers_for_download: int = 5
                            ) -> list[Path]:

    tile_ids = list(map(lambda x: x.split('/')[-1], urls))

    def extract_dest_path_from_url(tile_id):
        # glo DEMs
        if '.tif' in tile_id:
            return dest_dir / tile_id
        # USGS or NASA DEMs
        if '.zip' in tile_id:
            return dest_dir / tile_id.replace('.zip', '.tif')
        else:
            raise ValueError('The dataset format was not considered')

    dest_paths = list(map(extract_dest_path_from_url, tile_ids))
    reader = RASTER_READERS[dem_name]

    def download_and_write_one_partial(zipped_data: list) -> dict:
        return _download_and_write_one_tile_to_gtiff(zipped_data[0],
                                                     zipped_data[1],
                                                     reader,
                                                     dem_name)

    data_list = zip(urls, dest_paths)
    with ThreadPoolExecutor(max_workers=max_workers_for_download) as executor:
        list(tqdm(executor.map(download_and_write_one_partial, data_list),
                  total=len(urls),
                  desc=f'Downloading {dem_name} tiles'))

    dest_paths_str = list(map(str, dest_paths))
    return dest_paths_str


def get_dem_tile_paths(bounds: list[float],
                       dem_name: str,
                       localize_tiles_to_gtiff: bool = False,
                       n_threads_downloading: int = 5,
                       tile_dir: Union[str, Path] = None) -> list[str]:
    """Either:

    1. Gets (public urls) so that we can open with rasterio
    2. Localizes tiles as Geotiffs

    Can force localization setting `download_original_tiles` to True.

    Parameters
    ----------
    bounds : list
        [xmin, ymin, xmax, ymax] in epsg:4326 (i.e. x=lon and y=lat)
    dem_name : str
        One of the dems supported by the stitcher (use `from dem_stitcher.datasets import DATASETS; DATASETS`)
    localize_tiles_to_gtiff : bool, optional
        Localize DEM tiles as Geotiffs, by default False
    n_threads_downloading : int, optional
        Number of workers for downloading, by default 5
    tile_dir : Path | str, optional
        Directory to localize files, by default None, which saves to `dem_name`.

    Returns
    -------
    list[str]
        List of paths to dem as urls or paths on disk
    """

    df_tiles = get_overlapping_dem_tiles(bounds, dem_name)
    urls = df_tiles.url.tolist()

    if (not localize_tiles_to_gtiff):
        # Datasets that permit direct reading
        if (dem_name in ['glo_30', 'glo_90', '3dep', 'glo_90_missing']):
            dem_paths = urls
        else:
            warn(f'We need to localize the tiles as a Geotiff. Saving to {str(tile_dir)}',
                 category=UserWarning)

    if (dem_name not in ['glo_30', 'glo_90', '3dep', 'glo_90_missing']) or localize_tiles_to_gtiff:
        if isinstance(tile_dir, str):
            tile_dir = Path(tile_dir)
        if tile_dir is None:
            tile_dir = Path(dem_name)
        if tile_dir.exists():
            warn(f'The directory{tile_dir} exists; '
                 'We are writing new files to this directory',
                 category=UserWarning)
        tile_dir.mkdir(exist_ok=True, parents=True)
        dem_paths = download_tiles_to_gtiff(urls,
                                            dem_name,
                                            tile_dir,
                                            max_workers_for_download=n_threads_downloading)
    return dem_paths


def shift_profile_for_pixel_loc(src_profile: dict,
                                src_area_or_point: str,
                                dst_area_or_point: str) -> dict:
    assert dst_area_or_point in ['Area', 'Point']
    assert src_area_or_point in ['Area', 'Point']
    if (dst_area_or_point == 'Point') and (src_area_or_point == 'Area'):
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
                                  dst_resolution: Union[float, tuple[float]] = None,
                                  num_threads_reproj: int = 5,
                                  merge_nodata_value: float = np.nan) -> tuple[np.ndarray, dict]:
    dem_arr, dem_profile = merge_tile_datasets_within_extent(datasets,
                                                             bounds,
                                                             nodata=merge_nodata_value,
                                                             dtype=np.float32)
    # We could have merge_nodata_value that is zero and we want the final metadata
    # to be np.nan
    dem_profile['nodata'] = np.nan
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

    # Ensure dem_arr has correct shape
    assert len(dem_arr.shape) == 3

    return dem_arr, dem_profile


def patch_glo_30_with_glo_90(arr_glo_30: np.ndarray,
                             prof_glo_30: dict,
                             extent: list,
                             stitcher_kwargs: dict) -> tuple[np.ndarray, dict]:
    if not intersects_missing_glo_30_tiles(extent):
        return arr_glo_30, prof_glo_30

    stitcher_kwargs['dem_name'] = 'glo_90_missing'
    arr_glo_90, prof_glo_90 = stitch_dem(**stitcher_kwargs)

    # Dems internally are BIP with channel dimension exposed but stitcher api squeezes outputs
    dem_arr, dem_prof = merge_arrays_with_geometadata([arr_glo_30.squeeze(), arr_glo_90],
                                                      [prof_glo_30, prof_glo_90]
                                                      )

    return dem_arr, dem_prof


def _translate_one_tile_across_dateline(dataset: rasterio.DatasetReader, crossing):

    assert crossing in [180, -180]
    res_x = dataset.res[0]
    xmin, _, xmax, _ = dataset.bounds

    tags = dataset.tags()
    if crossing == 180 and xmax <= 0:
        memfile, dataset_new = translate_dataset(dataset, 360 / res_x, 0)
        # Ensures area or point are correctly stored!
        dataset_new.update_tags(**tags)
    elif crossing == -180 and xmin >= 0:
        memfile, dataset_new = translate_dataset(dataset, -360 / res_x, 0)
        # Ensures area or point are correctly stored!
        dataset_new.update_tags(**tags)
    else:
        memfile = MemoryFile()
        dataset_new = dataset

    return memfile, dataset_new


def stitch_dem(bounds: list,
               dem_name: str,
               dst_ellipsoidal_height: bool = True,
               dst_area_or_point: str = 'Area',
               dst_resolution: Union[float, tuple[float]] = None,
               n_threads_reproj: int = 5,
               n_threads_downloading: int = 5,
               fill_in_glo_30: bool = True,
               merge_nodata_value: float = np.nan
               ) -> tuple[np.ndarray, dict]:
    """This is API for stitching DEMs. Specify bounds and various options to obtain a continuous raster.
    The output raster will be determined by availability of tiles. If no tiles are available over bounds,
    then NoDEMCoverage is raised.

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
    dst_resolution : float | tuple[float], optional
        Can be float (square pixel with float resolution) or (x_res, y_res). When None is specified,
        then the DEM tile resolution is used. By default None
    n_threads_reproj : int, optional
        Threads to use for reprojection, by default 5
    n_threads_downloading : int, optional
        Threads for downloading tiles, by default 5
    fill_in_glo_30 : bool, optional
        If `dem_name` is 'glo_30' then fills in missing `glo_30` tiles over Armenia and Azerbaijan with available
        `glo_90` tiles, by default True. If the extent falls inside of the missing `glo_30` tiles, then `glo_90` is
        upsample to 30 meters unless `dst_resolution` is specified.
    merge_nodata_value: float, optional
        When merging tiles, utilize a different nodata value. A value other than 0 or np.nan will raise a ValueError.
        When set to np.nan (default), all areas with nodata in tiles are consistently marked in output as such.
        When set to 0 and converting to ellipsoidal heights, all nodata areas will be filled in with geoid.
        When set to 0 and not converting to ellipsoidal heights, all nodata areas will be 0.

    Returns
    -------
    tuple[np.ndarray, dict]
        (DEM Array, metadata dictionary). The metadata dictionary can be used as in rasterio to write the array
        in a gdal compatible format. See the
        [notebooks](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/tree/dev/notebooks)
        for demonstrations.
    """
    # Used for filling in glo_30 missing tiles if needed
    stitcher_kwargs = locals()

    # This variable is used later to determine if there is intersection with
    # Missing glo_30 tiles. We do not want calling stitch_dem (again)
    # for filling and/or patching glo_30 tiles with glo_90 to raise coverage
    # exceptions
    if fill_in_glo_30:
        glo_90_missing_intersection = intersects_missing_glo_30_tiles(bounds)
        fill_in_glo_30 = fill_in_glo_30 and glo_90_missing_intersection

    if merge_nodata_value not in [np.nan, 0]:
        raise ValueError('np.nan and 0 are only acceptable merge_nodata_value')

    # Random unique identifier
    tmp_id = str(uuid.uuid4())
    tile_dir = Path(f'tmp_{tmp_id}')

    dem_paths = get_dem_tile_paths(bounds=bounds,
                                   dem_name=dem_name,
                                   localize_tiles_to_gtiff=False,
                                   n_threads_downloading=n_threads_downloading,
                                   tile_dir=tile_dir)

    with ThreadPoolExecutor(max_workers=n_threads_downloading) as executor:
        datasets = list(tqdm(executor.map(rasterio.open, dem_paths),
                             total=len(dem_paths),
                             desc=f'Reading {dem_name} Datasets'))

    if not datasets:
        # This is the case that an extent is entirely contained within glo_90
        # tiles that are missing from glo_30 (list of datasets is empty)
        if (dem_name == 'glo_30') and fill_in_glo_30:

            stitcher_kwargs['dem_name'] = 'glo_90_missing'
            # if dst_resolution is None, then make sure we upsample to 30 meter resolution
            dst_resolution = stitcher_kwargs['dst_resolution']
            stitcher_kwargs['dst_resolution'] = dst_resolution or 0.0002777777777777777775

            dem_arr, dem_profile = stitch_dem(**stitcher_kwargs)
            return dem_arr, dem_profile
        else:
            raise NoDEMCoverage(f'Specified bounds are not within coverage area of {dem_name}')

    # Preserve tile metadata data not used for geo-referencing
    profile_tile = datasets[0].profile.copy()
    [profile_tile.pop(key) for key in ['transform', 'dtype', 'height', 'width', 'nodata', 'crs']]

    crossing = get_dateline_crossing(bounds)
    if crossing:
        zipped_data = list(map(lambda ds: _translate_one_tile_across_dateline(ds, crossing), datasets))
        memory_files, datasets = zip(*zipped_data)

    dem_arr, dem_profile = merge_and_transform_dem_tiles(datasets,
                                                         bounds,
                                                         dem_name,
                                                         dst_ellipsoidal_height=dst_ellipsoidal_height,
                                                         dst_area_or_point=dst_area_or_point,
                                                         dst_resolution=dst_resolution,
                                                         num_threads_reproj=n_threads_reproj,
                                                         merge_nodata_value=merge_nodata_value
                                                         )

    # Close datasets
    list(map(lambda dataset: dataset.close(), datasets))

    # Delete orginal tiles if downloaded
    if tile_dir.exists():
        shutil.rmtree(str(tile_dir))

    # Created in memory file containers if there is a dateline crossing for translation
    if crossing:
        list(map(lambda mf: mf.close(), memory_files))

    # This is the case when we have overlap of the requested extent and glo_30
    # and glo_90 tiles that are missing from glo_30.
    if (dem_name == 'glo_30') and fill_in_glo_30:
        dem_arr, dem_profile = patch_glo_30_with_glo_90(dem_arr,
                                                        dem_profile,
                                                        bounds,
                                                        stitcher_kwargs)

    dem_profile.update(**profile_tile)
    dem_arr = dem_arr[0, ...]
    return dem_arr, dem_profile
