import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple

import geopandas as gpd
import numpy as np
import rasterio
from osgeo import gdal
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import aligned_target
from rasterio.warp import reproject
from shapely.geometry import box
from tqdm import tqdm

from .datasets import get_dem_tile_extents
from .dem_readers import read_dem, read_glo, read_nasadem, read_ned1, read_srtm
from .geoid import remove_geoid
from .rio_tools import gdal_translate_profile, translate_profile

RASTER_READERS = {'ned1': read_ned1,
                  '3dep': read_dem,
                  'glo_30': read_glo,
                  'srtm_v3': read_srtm,
                  'nasadem': read_nasadem}

DEM2GEOID = {'ned1': 'geoid_18',
             '3dep': 'geoid_18',
             'glo_30': 'egm_08',
             'srtm_v3': 'egm_96',
             'nasadem': 'egm_96'}


def get_dem_tiles(bounds: list, dem_name: str) -> gpd.GeoDataFrame:
    box_sh = box(*bounds)
    df_tiles_all = get_dem_tile_extents(dem_name)
    index = df_tiles_all.intersects(box_sh)
    df_tiles = df_tiles_all[index].copy()

    # Merging is order dependent - ensures consistency
    df_tiles.sort_values(by='tile_id')
    df_tiles = df_tiles.reset_index(drop=True)
    return df_tiles


def download_tiles(urls: list,
                   dem_name: str,
                   dest_dir: Path,
                   max_workers: int = 5
                   ) -> List[Path]:

    tile_ids = list(map(lambda x: x.split('/')[-1], urls))
    dest_paths = list(map(lambda tile_id: dest_dir/f'{tile_id}.tif',
                          tile_ids))
    reader = RASTER_READERS[dem_name]

    def download_and_write_one(url, dest_path):
        dem_arr, dem_profile = reader(url)
        # if dem_arr is None - the tile does not exist - this is the case
        # for glo30
        if dem_arr is None:
            return

        dem_profile['driver'] = 'GTiff'
        with rasterio.open(dest_path, 'w', **dem_profile) as ds:
            ds.write(dem_arr, 1)
        return dem_profile

    def download_and_write_one_z(data: list) -> dict:
        return download_and_write_one(*data)

    data_list = zip(urls, dest_paths)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(tqdm(executor.map(download_and_write_one_z, data_list),
                            total=len(urls),
                            desc=f'Downloading {dem_name} tiles'))
    profiles = results

    n = len(dest_paths)
    dest_paths_f = [dest_paths[k] for k in range(n) if profiles[k] is not None]

    return dest_paths_f


def merge_tiles(datasets: List[rasterio.DatasetReader],
                bounds: list = None,
                resampling: str = 'nearest',
                nodata: float = np.nan
                ) -> Tuple[np.ndarray, dict]:
    if str(datasets[0].profile['dtype']) == 'int16':
        nodata = datasets[0].profile['nodata']
    merged_arr, merged_transform = merge(datasets,
                                         bounds=bounds,
                                         resampling=Resampling[resampling],
                                         nodata=nodata,
                                         dtype=str(datasets[0].profile['dtype']),
                                         target_aligned_pixels=True,
                                         res=datasets[0].res[-1]
                                         )
    # reshape to square pixels, if necessary
    new_transform, new_width, new_height = aligned_target(merged_transform,
                                                          merged_arr.shape[2],
                                                          merged_arr.shape[1],
                                                          datasets[0].res[-1])
    dst_arr = np.empty((1, new_height, new_width), dtype=datasets[0].profile['dtype'])
    merged_arr, merged_transform = reproject(merged_arr,
                                             dst_arr,
                                             src_crs=datasets[0].profile['crs'],
                                             dst_crs=CRS.from_epsg(4326),
                                             src_transform=merged_transform,
                                             dst_transform=new_transform,
                                             resampling=Resampling[resampling],
                                             dst_resolution=datasets[0].res[-1]
                                             )

    merged_arr = merged_arr[0, ...]
    profile = datasets[0].profile.copy()
    profile['height'] = merged_arr.shape[0]
    profile['width'] = merged_arr.shape[1]
    profile['nodata'] = nodata
    profile['dtype'] = str(datasets[0].profile['dtype'])
    profile['transform'] = merged_transform
    return merged_arr, profile


def gdal_merge_tiles(datasets: list,
                     res: float = None,
                     bounds: list = None,
                     nodata: float = np.nan,
                     driver: str = 'ISCE',
                     filepath: str = None,
                     resampling: str = 'near',
                     ) -> Tuple[np.ndarray, dict]:
    from affine import Affine

    gdal.BuildVRT(f'{filepath}_uncropped.vrt', datasets)
    gdal.Warp(filepath,
              f'{filepath}_uncropped.vrt',
              options=gdal.WarpOptions(format=driver,
                                       outputBounds=bounds,
                                       dstNodata=None,
                                       dstSRS=CRS.from_epsg(4326),
                                       xRes=res,
                                       yRes=res,
                                       resampleAlg=resampling,
                                       targetAlignedPixels=True,
                                       multithread=True)
              )

    with rasterio.open(filepath) as read_dataset:
        merged_arr = read_dataset.read(1)
        profile = read_dataset.profile
        
    # set nodata to 0 to avoid interpolation issues
    merged_arr[merged_arr == nodata] = 0
    profile['nodata'] = None

    # update geotrans
    trans_list = gdal.Open(filepath).GetGeoTransform()
    transform_cropped = Affine.from_gdal(*trans_list)
    profile['transform'] = transform_cropped
    
    # delete uncropped file
    os.remove(f'{filepath}_uncropped.vrt')

    return merged_arr, profile


def shift_profile_for_pixel_loc(src_profile: dict,
                                src_area_or_point: str,
                                dst_area_or_point: str, ) -> dict:
    assert(dst_area_or_point in ['Area', 'Point'])
    assert(src_area_or_point in ['Area', 'Point'])
    # no shift if SRTMv3 or NASADEM
    if dst_area_or_point == 'Point' and src_area_or_point == 'Area':
        x_shift = 1
        y_shift = 1
        profile_shifted = translate_profile(src_profile, x_shift, y_shift)
    elif (dst_area_or_point == 'Area') and (src_area_or_point == 'Point'):
        shift = .5
        profile_shifted = translate_profile(src_profile, shift, shift)
    # half shift down if glo30
    elif (dst_area_or_point == 'Point') and (src_area_or_point == 'Point'):
        x_shift = 1
        y_shift = 1
        profile_shifted = translate_profile(src_profile, x_shift, y_shift)
    else:
        profile_shifted = src_profile.copy()
    return profile_shifted


def gdal_shift_profile_for_pixel_loc(filepath: str,
                                     src_area_or_point: str,
                                     dst_area_or_point: str,
                                     input_array: np.ndarray,
                                     src_profile: dict) -> Tuple[np.ndarray, dict]:
    assert(dst_area_or_point in ['Area', 'Point'])
    assert(src_area_or_point in ['Area', 'Point'])
    # no shift if SRTMv3 or NASADEM
    if dst_area_or_point == 'Point' and src_area_or_point == 'Area':
        x_shift = 1
        y_shift = 1
        array_shifted, profile_shifted = gdal_translate_profile(filepath, x_shift, y_shift)
    elif (dst_area_or_point == 'Area') and (src_area_or_point == 'Point'):
        shift = .5
        array_shifted, profile_shifted = gdal_translate_profile(filepath, shift, shift)
    # half shift down if glo30
    elif (dst_area_or_point == 'Point') and (src_area_or_point == 'Point'):
        x_shift = 1
        y_shift = 1
        array_shifted, profile_shifted = gdal_translate_profile(filepath, x_shift, y_shift)
    else:
        array_shifted = input_array
        profile_shifted = src_profile.copy()
    return array_shifted, profile_shifted


def stitch_dem(bounds: list,
               dem_name: str,
               filepath: str,
               dst_ellipsoidal_height: bool = True,
               dst_area_or_point: str = 'Area',
               max_workers=5,
               driver: str = 'ISCE'):

    df_tiles = get_dem_tiles(bounds, dem_name)
    urls = df_tiles.url.tolist()
    tile_dir = Path('tmp')
    
    # Datasets that permit virtual warping
    # The readers return DatasetReader rather than (Array, Profile)
    if dem_name in ['glo_30', '3dep']:
        def reader(url):
            return RASTER_READERS[dem_name](url)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(tqdm(executor.map(reader, urls),
                                total=len(urls),
                                desc=f'Reading {dem_name} Datasets'))

        # If datasets are non-existent, returns None
        datasets = list(filter(lambda x: x is not None, results))
        # save tiles to dir for faster warping
        tile_dir.mkdir(exist_ok=True, parents=True)
        dest_paths = []
        # dem_arr, dem_profile = reader(url)
        for i in datasets:
            data_arr = i.read(1)
            dest_path = os.path.join('tmp', os.path.basename(i.name))
            dest_paths.append(dest_path)
            with rasterio.open(dest_path, 'w', **i.profile) as ds:
                ds.write(data_arr, 1)
    else:
        # save tiles to dir for faster warping
        tile_dir.mkdir(exist_ok=True, parents=True)
        dest_paths = download_tiles(urls,
                                    dem_name,
                                    tile_dir,
                                    max_workers=max_workers)
        datasets = list(map(rasterio.open, dest_paths))
        dest_paths = [str(i.resolve()) for i in dest_paths]

    nodata = np.array([datasets[0].profile['nodata']], \
                   dtype = datasets[0].profile['dtype'])[0]
    dem_arr, dem_profile = gdal_merge_tiles(dest_paths,
                                            datasets[0].res[-1],
                                            bounds=bounds,
                                            nodata=nodata,
                                            filepath=filepath,
                                            resampling='near')
    src_area_or_point = datasets[0].tags().get('AREA_OR_POINT', 'Area')

    # Close datasets
    list(map(lambda dataset: dataset.close(), datasets))

    if dem_profile['crs'] != CRS.from_epsg(4326):
        raise ValueError('CRS must be epsg 4269 or 4326')

    dem_arr, dem_profile = gdal_shift_profile_for_pixel_loc(filepath,
                                                            src_area_or_point,
                                                            dst_area_or_point,
                                                            dem_arr,
                                                            dem_profile)

    # set nodata to 0 to avoid interpolation issues
    dem_arr[dem_arr == nodata] = 0
    dem_profile['nodata'] = None
    # create mask to apply later
    dem_mask = np.zeros(dem_arr.shape)
    dem_mask[dem_arr != 0] = 1
    if dst_ellipsoidal_height:
        geoid_name = DEM2GEOID[dem_name]
        dem_arr = remove_geoid(dem_arr,
                               dem_profile,
                               geoid_name,
                               extent=bounds,
                               src_area_or_point=src_area_or_point,
                               dem_area_or_point=dst_area_or_point,
                               filepath=filepath)

    # apply mask
    dem_arr[dem_mask == 0] = 0
    # update DEM array in file
    update_file = gdal.Open(filepath, gdal.GA_Update)
    update_file.GetRasterBand(1).WriteArray(dem_arr)
    del update_file

    dem_profile['driver'] = driver

    # Delete original tiles if downloaded
    if tile_dir.exists():
        shutil.rmtree(str(tile_dir))
