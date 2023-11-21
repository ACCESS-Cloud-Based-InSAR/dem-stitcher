from typing import Union

import numpy as np
from affine import Affine
from rasterio import DatasetReader
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.warp import (Resampling, aligned_target,
                           calculate_default_transform, reproject)


def translate_profile(profile: dict,
                      x_shift: float,
                      y_shift: float,
                      ) -> dict:
    """Shift profile

    Parameters
    ----------
    profile : dict
        Rasterio profile
    x_shift : float
        Number of pixels to translate by in x-direction
    y_shift : float
        Number of pixels to translate by in y-direction

    Returns
    -------
    dict
        Rasterio profile with transform shifted
    """
    transform = profile['transform']

    new_origin = transform * (x_shift, y_shift)
    new_transform = Affine.translation(*new_origin)
    new_transform = new_transform * transform.scale(transform.a,
                                                    transform.e)

    p_new = profile.copy()
    p_new['transform'] = new_transform

    return p_new


def translate_dataset(dataset: DatasetReader,
                      x_shift: float,
                      y_shift: float) -> tuple[MemoryFile, DatasetReader]:
    """Creates a new in-memory dataset and translates this. Closes the input dataset.

    Parameters
    ----------
    dataset : DatasetReader
        Input dataset in read mode. Will be closed after function is run.
    x_shift : float
        Number of *pixels* to be translated
    y_shift : float
        Number of *pixels* to be translated

    Returns
    -------
    Tuple[MemoryFile, DatasetReader]
        Memory file and DatasetReader in Rasterio
    """

    memfile = MemoryFile()
    profile = dataset.profile
    profile_translated = translate_profile(profile, x_shift=x_shift, y_shift=y_shift)
    dataset_new = memfile.open(**profile_translated)
    dataset_new.write(dataset.read())
    dataset.close()

    return memfile, dataset_new


def reproject_arr_to_match_profile(src_array: np.ndarray,
                                   src_profile: dict,
                                   ref_profile: dict,
                                   nodata: Union[float, int] = None,
                                   num_threads: int = 1,
                                   resampling='bilinear') -> tuple[np.ndarray, dict]:
    """
    Reprojects an array to match a reference profile providing the reprojected
    array and the new profile.  Simply a wrapper for rasterio.warp.reproject.

    Parameters
    ----------
    src_array : np.ndarray
        The source array to be reprojected.
    src_profile : dict
        The source profile of the `src_array`
    ref_profile : dict
        The reference profile whose geo-metadata will be resampled into.
    nodata : Union[int, float]
        The nodata value to be used in output profile. If None, the nodata from
        src_profile is used in the output profile. Thus, update `src_profile['nodata']= None` to
        ensure None can be used.
    num_threads: int
        gdal allows for multiple threads for resampling
    resampling : str
        The type of resampling to use. See all the options:
        https://github.com/rasterio/rasterio/blob/master/rasterio/enums.py#L48-L82

    Returns
    -------
    Tuple[np.ndarray, dict]:
        Reprojected Arr, Reprojected Profile

    Notes
    -----
    src_array needs to be in gdal (i.e. BIP) format that is (# of channels) x
    (vertical dim.) x (horizontal dim).  Also, works with arrays of the form
    (vertical dim.) x (horizontal dim), but output will be: 1 x (vertical dim.)
    x (horizontal dim).
    """
    dst_crs = ref_profile['crs']
    dst_transform = ref_profile['transform']

    reproject_profile = ref_profile.copy()

    nodata = nodata or src_profile['nodata']
    src_dtype = src_profile['dtype']
    count = src_profile['count']

    reproject_profile.update({'dtype': src_dtype,
                              'nodata': nodata,
                              'count': count})

    height, width = ref_profile['height'], ref_profile['width']
    dst_array = np.zeros((count, height, width))

    reproject(src_array,
              dst_array,
              src_transform=src_profile['transform'],
              src_crs=src_profile['crs'],
              dst_transform=dst_transform,
              dst_crs=dst_crs,
              dst_nodata=nodata,
              resampling=Resampling[resampling],
              num_threads=num_threads
              )
    return dst_array.astype(src_dtype), reproject_profile


def get_bounds_dict(profile: dict) -> dict:
    """
    Get the dictionary with bounds in the relevant CRS with keys 'left',
    'right', 'top', 'bottom'.

    Parameters
    ----------
    profile : dict
        The rasterio reference profile

    Returns
    -------
    dict:
        The bounds dictionary.
    """
    lx, ly = profile['width'], profile['height']
    transform = profile['transform']
    bounds_dict = {'left': transform.c,
                   'right': transform.c + transform.a * lx,
                   'top': transform.f,
                   'bottom': transform.f + transform.e * ly
                   }
    return bounds_dict


def reproject_profile_to_new_crs(src_profile: dict, dst_crs: CRS,
                                 target_resolution: Union[float, int] = None)\
                                         -> dict:
    """
    Create a new profile into a new CRS based on a dst_crs. May specify
    resolution.

    Parameters
    ----------
    src_profile : dict
        Source rasterio profile.
    dst_crs : str
        Destination CRS, as specified by rasterio.
    target_resolution : Union[float, int]
        Target resolution

    Returns
    -------
    dict:
        Rasterio profile of new CRS
    """
    reprojected_profile = src_profile.copy()
    bounds_dict = get_bounds_dict(src_profile)

    src_crs = src_profile['crs']
    w, h = src_profile['width'], src_profile['height']
    dst_trans, dst_w, dst_h = calculate_default_transform(src_crs,
                                                          dst_crs,
                                                          w, h,
                                                          **bounds_dict
                                                          )

    if target_resolution is not None:
        tr = target_resolution
        dst_trans, dst_w, dst_h = aligned_target(dst_trans,
                                                 dst_w,
                                                 dst_h,
                                                 tr)
    reprojected_profile.update({
                                'crs': dst_crs,
                                'transform': dst_trans,
                                'width': dst_w,
                                'height': dst_h,
                                })
    return reprojected_profile


def reproject_arr_to_new_crs(src_array: np.ndarray,
                             src_profile: dict,
                             dst_crs: str,
                             resampling: str = 'bilinear',
                             target_resolution: float = None) -> \
                                     tuple[np.ndarray, dict]:
    """
    Reproject an array into a new CRS.

    Parameters
    ----------
    src_array : np.ndarray
        Source array
    src_profile : dict
        Source rasterio profile corresponding to `src_array`
    dst_crs : str
        The destination rasterio CRS to reproject into
    resampling : str
        See all the options:
        https://github.com/rasterio/rasterio/blob/master/rasterio/enums.py#L48-L82
    target_resolution : float
        Target resolution

    Returns
    -------
    Tuple[np.ndarray, dict]:
        (reprojected_array, reprojected_profile) of data.
    """
    tr = target_resolution
    reprojected_profile = reproject_profile_to_new_crs(src_profile,
                                                       dst_crs,
                                                       target_resolution=tr)
    resampling = Resampling[resampling]
    dst_array = np.zeros((reprojected_profile['count'],
                          reprojected_profile['height'],
                          reprojected_profile['width']))

    reproject(
              # Source parameters
              source=src_array,
              src_crs=src_profile['crs'],
              src_transform=src_profile['transform'],
              # Destination paramaters
              destination=dst_array,
              dst_transform=reprojected_profile['transform'],
              dst_crs=reprojected_profile['crs'],
              dst_nodata=src_profile['nodata'],
              # Configuration
              resampling=resampling,
              )
    return dst_array, reprojected_profile


def _aligned_target(transform: Affine,
                    width: int, height: int,
                    resolution: Union[float, int, tuple]):
    """Aligns target to specified resolution; ensures same origin.
    Source: https://github.com/rasterio/rasterio/blob/master/rasterio/warp.py#L354-L393

    Parameters
    ----------
    transform : Affine
        Input affine transformation matrix
    width, height: int
        Input dimensions
    resolution: tuple (x resolution, y resolution) or float or int
        Target resolution, in units of target coordinate reference
        system.
    Returns
    -------
    transform: Affine
        Output affine transformation matrix
    width, height: int
        Output dimensions
    """
    if isinstance(resolution, (float, int)):
        res = (float(resolution), float(resolution))
    else:
        res = resolution

    xmin = transform.xoff
    ymin = transform.yoff + height * transform.e
    xmax = transform.xoff + width * transform.a
    ymax = transform.yoff

    dst_transform = Affine(res[0], 0, xmin, 0, -res[1], ymax)
    dst_width = max(int(np.floor((xmax - xmin) / res[0])), 1)
    dst_height = max(int(np.floor((ymax - ymin) / res[1])), 1)

    return dst_transform, dst_width, dst_height


def update_profile_resolution(src_profile: dict,
                              resolution: Union[float, tuple[float]]) -> dict:
    transform = src_profile['transform']
    width = src_profile['width']
    height = src_profile['height']

    dst_transform, dst_width, dst_height = _aligned_target(transform,
                                                           width,
                                                           height,
                                                           resolution)

    dst_profile = src_profile.copy()
    dst_profile['width'] = dst_width
    dst_profile['height'] = dst_height
    dst_profile['transform'] = dst_transform

    return dst_profile
