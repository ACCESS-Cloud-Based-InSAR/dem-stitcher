import io
import zipfile
from typing import Tuple

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile


def read_dem(dem_path: str) -> rasterio.DatasetReader:
    with rasterio.open(dem_path) as ds:
        dem_arr = ds.read()
        dem_profile = ds.profile
    return dem_arr, dem_profile


def read_dem_bytes(dem_path: str, suffix: str = '.img') -> bytes:
    # online
    if (dem_path[:7] == 'http://') or (dem_path[:8] == 'https://'):
        resp = requests.get(dem_path)
        data = io.BytesIO(resp.content)
    # local file
    else:
        data = dem_path
    zip_ob = zipfile.ZipFile(data)

    filenames = zip_ob.filelist

    # There is a unique *.img file
    n = len(suffix)
    img_ob = list(filter(lambda x: x.filename[-n:] == suffix, filenames))[0]
    img_bytes = zip_ob.read(img_ob)

    return img_bytes


def read_srtm(dem_path: str, version='srtm') -> Tuple[np.ndarray, dict]:
    img_bytes = read_dem_bytes(dem_path, suffix='.hgt')
    # The gdal driver hgt depends on filename convention
    filename = dem_path.split('/')[-1]
    if version == 'srtm':
        filename = filename.replace('.zip', '')
    elif version == 'nasadem':
        filename = filename.replace('.zip', '.hgt')
        filename = filename.replace('NASADEM_HGT_', '')
    else:
        raise ValueError('version must be either nasadem or srtm')

    with MemoryFile(img_bytes, filename=filename) as memfile:
        with memfile.open() as dataset:
            dem_arr = dataset.read().astype(np.float32)
            dem_profile = dataset.profile

    return dem_arr, dem_profile


def read_nasadem(dem_path: str) -> Tuple[np.ndarray, dict]:
    return read_srtm(dem_path, version='nasadem')
