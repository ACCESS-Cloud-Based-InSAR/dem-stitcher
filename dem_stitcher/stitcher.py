from pathlib import Path
from rasterio.enums import Resampling
from tqdm import tqdm
import geopandas as gpd
import rasterio
from rasterio.merge import merge
# from rasterio.warp import Resampling
from rasterio.crs import CRS
from shapely.geometry import box
from typing import Tuple, List
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from lxml import etree
import shutil

from .dem_readers import read_dem, read_ned1, read_glo, read_srtm, read_nasadem
from .rio_tools import (translate_profile,
                        reproject_arr_to_new_crs,
                        )
from .geoid import remove_geoid
from .datasets import get_dem_tile_extents

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
                resampling: str = 'bilinear',
                nodata: float = np.nan
                ) -> Tuple[np.ndarray, dict]:
    merged_arr, merged_transform = merge(datasets,
                                         bounds=bounds,
                                         resampling=Resampling[resampling],
                                         nodata=nodata,
                                         dtype='float32',
                                         target_aligned_pixels=True,
                                         )
    merged_arr = merged_arr[0, ...]

    profile = datasets[0].profile.copy()
    profile['height'] = merged_arr.shape[0]
    profile['width'] = merged_arr.shape[1]
    profile['nodata'] = nodata
    profile['dtype'] = 'float32'
    profile['transform'] = merged_transform
    return merged_arr, profile


def shift_profile_for_pixel_loc(src_profile: dict,
                                src_area_or_point: str,
                                dst_area_or_point: str, ):
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


def stitch_dem(bounds: list,
               dem_name: str,
               dst_ellipsoidal_height: bool = True,
               dst_area_or_point: str = 'Point',
               max_workers=5,
               driver: str = 'GTiff'
               ) -> Tuple[np.ndarray, dict]:

    df_tiles = get_dem_tiles(bounds, dem_name)
    urls = df_tiles.url.tolist()
    tile_dir = Path('tmp')

    # Datasets that permit virtual warping
    # The readers return DatasetReader rather than Arr, Prof
    if dem_name in ['glo_30', '3dep']:
        def reader(url):
            return RASTER_READERS[dem_name](url)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
                                    max_workers=max_workers)
        datasets = list(map(rasterio.open, dest_paths))

    dem_arr, dem_profile = merge_tiles(datasets,
                                       bounds=bounds,
                                       nodata=np.nan)
    src_area_or_point = datasets[0].tags().get('AREA_OR_POINT', 'Area')

    # Close datasets
    list(map(lambda dataset: dataset.close(), datasets))

    # Delete orginal tiles if downloaded
    if tile_dir.exists():
        shutil.rmtree(str(tile_dir))

    # Reproject to 4326
    if dem_profile['crs'] == CRS.from_epsg(4269):
        dem_arr, dem_profile = reproject_arr_to_new_crs(dem_arr,
                                                        dem_profile,
                                                        CRS.from_epsg(4326))
        dem_arr = dem_arr[0, ...]

    if dem_profile['crs'] != CRS.from_epsg(4326):
        raise ValueError('CRS must be epsg 4269 or 4326')

    dem_profile = shift_profile_for_pixel_loc(dem_profile,
                                              src_area_or_point,
                                              dst_area_or_point)

    if dst_ellipsoidal_height:
        geoid_name = DEM2GEOID[dem_name]
        dem_arr = remove_geoid(dem_arr,
                               dem_profile,
                               geoid_name,
                               extent=bounds,
                               dem_area_or_point=dst_area_or_point,
                               )

    dem_profile['driver'] = driver
    return dem_arr, dem_profile


def tag_dem_xml_as_ellipsoidal(dem_path: Path) -> str:
    xml_path = str(dem_path) + '.xml'
    assert(Path(xml_path).exists())
    tree = etree.parse(xml_path)
    root = tree.getroot()

    y = etree.Element("property", name='reference')
    etree.SubElement(y, "value").text = "WGS84"
    etree.SubElement(y, "doc").text = "Geodetic datum"

    root.insert(0, y)
    with open(xml_path, 'wb') as file:
        file.write(etree.tostring(root, pretty_print=True))
    return xml_path


def stitch_dem_for_isce2(bounds: list,
                         dem_name: str,
                         dst_path: str = None,
                         nodata: float = 0
                         ) -> Path:

    dem_arr, dem_profile = stitch_dem(bounds,
                                      dem_name,
                                      dst_ellipsoidal_height=True,
                                      dst_area_or_point='Point',
                                      max_workers=5,
                                      )

    dst_path = dst_path or f'{dem_name}.wgs.84'
    out_path = Path(dst_path)

    dem_profile['driver'] = 'ISCE'
    dem_profile['nodata'] = nodata
    dem_arr[np.isnan(dem_arr)] = nodata

    with rasterio.open(out_path, 'w', **dem_profile) as ds:
        ds.write(dem_arr, 1)
        ds.update_tags(AREA_OR_POINT='Point')

    tag_dem_xml_as_ellipsoidal(out_path)

    return out_path
