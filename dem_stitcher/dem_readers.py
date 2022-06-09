import io
import zipfile
from typing import Tuple

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile


def read_dem(url: str) -> rasterio.DatasetReader:
    ds = rasterio.open(url)
    return ds


def read_dem_bytes(url: str, suffix: str = '.img') -> bytes:
    # online
    if (url[:7] == 'http://') or (url[:8] == 'https://'):
        resp = requests.get(url)
        data = io.BytesIO(resp.content)
    # local file
    else:
        data = url
    zip_ob = zipfile.ZipFile(data)

    filenames = zip_ob.filelist

    # There is a unique *.img file
    n = len(suffix)
    img_ob = list(filter(lambda x: x.filename[-n:] == suffix, filenames))[0]
    img_bytes = zip_ob.read(img_ob)

    return img_bytes


def read_ned1(url: str) -> Tuple[np.ndarray, dict]:
    img_bytes = read_dem_bytes(url, suffix='.img')
    with MemoryFile(img_bytes) as memfile:
        with memfile.open() as dataset:
            dem_arr = dataset.read(1)
            dem_profile = dataset.profile

    return dem_arr, dem_profile


def read_srtm(url: str, version='srtm') -> Tuple[np.ndarray, dict]:
    img_bytes = read_dem_bytes(url, suffix='.hgt')
    # The gdal driver hgt depends on filename convention
    filename = url.split('/')[-1]
    if version == 'srtm':
        filename = filename.replace('.zip', '')
    elif version == 'nasadem':
        filename = filename.replace('.zip', '.hgt')
        filename = filename.replace('NASADEM_HGT_', '')
    else:
        raise ValueError('version must be either nasadem or srtm')

    with MemoryFile(img_bytes, filename=filename) as memfile:
        with memfile.open() as dataset:
            dem_arr = dataset.read(1).astype(np.float32)
            dem_profile = dataset.profile

    return dem_arr, dem_profile


def read_nasadem(url: str) -> Tuple[np.ndarray, dict]:
    return read_srtm(url, version='nasadem')
