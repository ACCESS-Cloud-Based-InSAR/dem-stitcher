from pathlib import Path
from tqdm import tqdm
import geopandas as gpd
import rasterio
from rasterio.merge import merge
from rasterio import default_gtiff_profile
# from rasterio.warp import Resampling
from rasterio.crs import CRS
from shapely.geometry import box
from typing import Union
import warnings
import numpy as np
from concurrent.futures import ThreadPoolExecutor

from .dem_readers import read_dem, read_ned1, read_glo, read_srtm, read_nasadem
from .rio_tools import (translate_profile,
                        crop_profile_from_coord_bounds,
                        reproject_arr_to_new_crs,
                        reproject_arr_to_match_profile,
                        )
from .geoid import remove_geoid
from .datasets import get_dem_tile_extents

RASTER_READERS = {'ned1': read_ned1,
                  '3dep': read_dem,
                  'glo_30': read_glo,
                  'srtm_v3': read_srtm,
                  'nasadem': read_nasadem}

PIXEL_AS_AREA = {'ned1': True,
                 '3dep': True,
                 'glo_30': False,
                 'srtm_v3': False,
                 'nasadem': False}

DEM2GEOID = {'ned1': 'geoid_18',
             '3dep': 'geoid_18',
             'glo_30': 'egm_08',
             'srtm_v3': 'egm_96',
             'nasadem': 'egm_96'}


def download_tiles(df_tiles: gpd.GeoDataFrame,
                   dest_dir: Path,
                   max_workers: int = 5
                   ) -> tuple:

    if max_workers > 5:
        warnings.warn('Max workers greater than 5 could cause Timeout Errors')

    urls = df_tiles.url.tolist()
    tile_ids = df_tiles.tile_id.tolist()
    dem_name = df_tiles.dem_name.tolist()[0]

    reader = RASTER_READERS[dem_name]

    dest_paths = list(map(lambda tile_id: dest_dir/f'{dem_name}_{tile_id}.tif',
                          tile_ids))

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

    def download_and_write_one_z(data):
        return download_and_write_one(*data)

    data_list = zip(urls, dest_paths)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(tqdm(executor.map(download_and_write_one_z, data_list),
                            total=len(urls),
                            desc=f'Downloading {dem_name} tiles'))
    profiles = results

    n = len(dest_paths)
    dest_paths_f = [dest_paths[k] for k in range(n) if profiles[k] is not None]
    profiles_f = [profiles[k] for k in range(n) if profiles[k] is not None]

    return dest_paths_f, profiles_f


def merge_tiles(paths):
    datasets = list(map(rasterio.open, paths))
    merged_arr, merged_transform = merge(datasets)
    merged_arr = merged_arr[0, ...]
    list(map(lambda dataset: dataset.close(), datasets))

    profile = default_gtiff_profile.copy()
    with rasterio.open(paths[0]) as ds:
        crs = ds.crs

    profile['height'] = merged_arr.shape[0]
    profile['width'] = merged_arr.shape[1]
    profile['transform'] = merged_transform
    profile['crs'] = crs
    profile['count'] = 1
    profile['dtype'] = 'float32'
    profile['nodata'] = np.nan

    return merged_arr, profile


def download_dem(bounds: list,
                 dem_name: str,
                 dest_dir: Union[str, Path],
                 ellipsoidal_height: bool = False,
                 save_raw_tiles: bool = False,
                 dst_area_or_point: str = 'Point',
                 dest_driver: str = 'ISCE',
                 max_workers: int = 5,
                 force_agi_read_for_geoid: bool = False,
                 ) -> Path:
    if isinstance(dest_dir, str):
        dest_dir = Path(dest_dir)

    if dest_dir.exists():
        warnings.warn(f'{dest_dir} exists; data will be overwritten')
    dest_dir.mkdir(exist_ok=True, parents=True)

    # Get tiles to download
    box_sh = box(*bounds)
    df_tiles_all = get_dem_tile_extents(dem_name)
    index = df_tiles_all.intersects(box_sh)
    df_tiles = df_tiles_all[index].copy()

    # Merging is order dependent - ensures consistency
    df_tiles.sort_values(by='tile_id')
    df_tiles = df_tiles.reset_index(drop=True)

    # Download tiles and merge
    tile_paths, _ = download_tiles(df_tiles, dest_dir, max_workers=max_workers)
    dem_arr, dem_profile = merge_tiles(tile_paths)
    if not save_raw_tiles:
        list(map(lambda path: path.unlink(), tile_paths))

    assert(dst_area_or_point in ['Area', 'Point'])
    if dst_area_or_point == 'Point' and PIXEL_AS_AREA.get(dem_name):
        shift = -.5
        dem_profile = translate_profile(dem_profile, shift, shift)
    if dst_area_or_point == 'Area' and not PIXEL_AS_AREA.get(dem_name):
        shift = .5
        dem_profile = translate_profile(dem_profile, shift, shift)

    # Reproject to 4326
    if dem_profile['crs'] == CRS.from_epsg(4269):
        dem_arr, dem_profile = reproject_arr_to_new_crs(dem_arr,
                                                        dem_profile,
                                                        CRS.from_epsg(4326))

        # dst_profile_4326 = dem_profile.copy()
        # dst_profile_4326['crs'] = CRS.from_epsg(4326)
        # dem_arr, dem_profile = reproject_arr_to_match_profile(dem_arr,
        #                                                       dem_profile,
        #                                                       dst_profile_4326)
    elif dem_profile['crs'] != CRS.from_epsg(4326):
        raise ValueError('CRS must be epsg 4269 or 4326')

    # Fit to bounds
    profile_cropped = crop_profile_from_coord_bounds(dem_profile, bounds)
    dem_arr, dem_profile = reproject_arr_to_match_profile(dem_arr,
                                                          dem_profile,
                                                          profile_cropped)

    dem_arr = dem_arr[0, ...]

    # Remove Geoid - must be done after point/area translation
    if ellipsoidal_height:
        geoid_name = DEM2GEOID[dem_name]
        dem_arr = remove_geoid(dem_arr,
                               dem_profile,
                               geoid_name,
                               extent=bounds,
                               dem_area_or_point=dst_area_or_point,
                               force_agi_read=force_agi_read_for_geoid
                               )

    out_path = dest_dir/f'{dem_name}.dem.wgs84'
    dem_profile['driver'] = dest_driver
    with rasterio.open(out_path, 'w', **dem_profile) as ds:
        ds.write(dem_arr, 1)
        ds.update_tags(AREA_OR_POINT=dst_area_or_point)

    return out_path
