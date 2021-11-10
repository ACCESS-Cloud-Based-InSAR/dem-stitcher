import rasterio
import requests
import zipfile
from rasterio.io import MemoryFile
import numpy as np
import io
from typing import Union, Tuple
from rasterio import RasterioIOError


def read_dem(url: str) -> rasterio.DatasetReader:
    ds = rasterio.open(url)
    return ds


def read_glo(url: str) -> Union[rasterio.DatasetReader, None]:
    # Some tiles do not exist
    try:
        return read_dem(url)
    except RasterioIOError:
        return None


def read_dem_bytes(url: str, suffix: str = '.img') -> bytes:
    request = requests.get(url)
    zip_ob = zipfile.ZipFile(io.BytesIO(request.content))

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
