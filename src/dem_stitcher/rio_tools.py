from collections.abc import Callable
from functools import wraps

import numpy as np
import rasterio
from affine import Affine
from rasterio import DatasetReader
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.warp import Resampling, aligned_target, calculate_default_transform, reproject


GEOMETADATA_KEYS = ('driver', 'dtype', 'nodata', 'width', 'height', 'count', 'crs', 'transform')
# Without this, GDAL probes for sidecars (*.aux.xml, *.ovr, ...) next to every raster it opens, which for
# remote rasters (e.g. the ARIA geoids) are 403s that GDAL logs as warnings.
# See: https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/262
GDAL_READ_OPTIONS = {'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR'}


def gdal_read_env(**kwargs: str) -> rasterio.Env:
    """Get a rasterio environment with the GDAL options used for all raster reads in this library."""
    return rasterio.Env(**{**GDAL_READ_OPTIONS, **kwargs})


def with_gdal_read_env(func: Callable) -> Callable:
    """Run a read function within `gdal_read_env()`; nests safely within an outer `rasterio.Env`."""

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        with gdal_read_env():
            return func(*args, **kwargs)

    return wrapper


def in_memory_profile(profile: dict) -> dict:
    """Strip creation options (compression, tiling, interleaving) from a profile.

    In-memory datasets are written and then read back before they are closed. Creation options inherited from a
    source COG - notably `compress` - put GDAL into multi-threaded compression, whose queued writes are not
    reliably visible to those read backs when `GDAL_NUM_THREADS` is large.
    See: https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/157
    """
    return {**{key: profile[key] for key in GEOMETADATA_KEYS if key in profile}, 'driver': 'GTiff'}


def translate_profile(
    profile: dict,
    x_shift: float,
    y_shift: float,
) -> dict:
    """Shift profile by x and y pixels.

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
    new_transform = new_transform * transform.scale(transform.a, transform.e)

    p_new = profile.copy()
    p_new['transform'] = new_transform

    return p_new


def translate_dataset(dataset: DatasetReader, x_shift: float, y_shift: float) -> tuple[MemoryFile, DatasetReader]:
    """Create a new in-memory dataset and translates this. Closes the input dataset.

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
    dataset_new = memfile.open(**in_memory_profile(profile_translated))
    dataset_new.write(dataset.read())
    dataset.close()

    return memfile, dataset_new


def reproject_arr_to_match_profile(
    src_array: np.ndarray,
    src_profile: dict,
    ref_profile: dict,
    nodata: float | int = None,
    num_threads: int = 1,
    resampling: str = 'bilinear',
    preserve_rank: bool = False,
) -> tuple[np.ndarray, dict]:
    """
    Reproject an array to match a reference profile providing the reprojected array and the new profile.

    A wrapper for rasterio.warp.reproject.

    Parameters
    ----------
    src_array : np.ndarray
        The source array to be reprojected.
    src_profile : dict
        The source profile of the `src_array`
    ref_profile : dict
        The reference profile whose geo-metadata will be resampled into.
    nodata : int or float, optional
        The nodata value to be used in output profile. If None, the nodata from
        src_profile is used in the output profile. Thus, update `src_profile['nodata']= None` to
        ensure None can be used.
    num_threads : int, optional
        gdal allows for multiple threads for resampling
    resampling : str, optional
        The type of resampling to use. See all the options:
        https://github.com/rasterio/rasterio/blob/master/rasterio/enums.py#L48-L82
    preserve_rank : bool, optional
        If True, a 2D source array yields a 2D output array (and output profile with count 1).
        Default False preserves the historical behavior of always returning a 3D array.

    Returns
    -------
    tuple[np.ndarray, dict]
        Reprojected array, reprojected profile

    Raises
    ------
    ValueError
        If `src_array` is not 2 or 3 dimensional.

    Notes
    -----
    src_array needs to be in gdal (i.e. BIP) format that is (# of channels) x
    (vertical dim.) x (horizontal dim).  Also, works with arrays of the form
    (vertical dim.) x (horizontal dim), but output will be: 1 x (vertical dim.)
    x (horizontal dim) unless `preserve_rank=True`.
    """
    if src_array.ndim not in (2, 3):
        raise ValueError(f'src_array must be 2 or 3 dimensional; got shape {src_array.shape}')

    dst_crs = ref_profile['crs']
    dst_transform = ref_profile['transform']

    reproject_profile = ref_profile.copy()

    nodata = nodata or src_profile['nodata']
    src_dtype = src_profile['dtype']
    count = src_profile['count']

    height, width = ref_profile['height'], ref_profile['width']
    if preserve_rank and src_array.ndim == 2:
        count = 1
        dst_shape = (height, width)
    else:
        dst_shape = (count, height, width)

    reproject_profile.update({'dtype': src_dtype, 'nodata': nodata, 'count': count})

    dst_array = np.zeros(dst_shape, dtype=src_dtype)

    reproject(
        src_array,
        dst_array,
        src_transform=src_profile['transform'],
        src_crs=src_profile['crs'],
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=nodata,
        resampling=Resampling[resampling],
        num_threads=num_threads,
    )
    return dst_array, reproject_profile


def get_bounds_dict(profile: dict) -> dict:
    """
    Get the dictionary with bounds in the relevant CRS with keys 'left', 'right', 'top', 'bottom'.

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
    bounds_dict = {
        'left': transform.c,
        'right': transform.c + transform.a * lx,
        'top': transform.f,
        'bottom': transform.f + transform.e * ly,
    }
    return bounds_dict


def reproject_profile_to_new_crs(src_profile: dict, dst_crs: CRS, target_resolution: float | int = None) -> dict:
    """Create a new profile into a new CRS based on a dst_crs. May specify resolution.

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
    dst_trans, dst_w, dst_h = calculate_default_transform(src_crs, dst_crs, w, h, **bounds_dict)

    if target_resolution is not None:
        tr = target_resolution
        dst_trans, dst_w, dst_h = aligned_target(dst_trans, dst_w, dst_h, tr)
    reprojected_profile.update(
        {
            'crs': dst_crs,
            'transform': dst_trans,
            'width': dst_w,
            'height': dst_h,
        }
    )
    return reprojected_profile


def reproject_arr_to_new_crs(
    src_array: np.ndarray,
    src_profile: dict,
    dst_crs: str,
    resampling: str = 'bilinear',
    target_resolution: float = None,
    preserve_rank: bool = False,
) -> tuple[np.ndarray, dict]:
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
    resampling : str, optional
        See all the options:
        https://github.com/rasterio/rasterio/blob/master/rasterio/enums.py#L48-L82
    target_resolution : float, optional
        Target resolution
    preserve_rank : bool, optional
        If True, a 2D source array yields a 2D output array (and output profile with count 1).
        Default False preserves the historical behavior of always returning a 3D array
        of shape (count) x (vertical dim.) x (horizontal dim.).

    Returns
    -------
    tuple[np.ndarray, dict]
        (reprojected_array, reprojected_profile) of data.

    Raises
    ------
    ValueError
        If `src_array` is not 2 or 3 dimensional.
    """
    if src_array.ndim not in (2, 3):
        raise ValueError(f'src_array must be 2 or 3 dimensional; got shape {src_array.shape}')

    tr = target_resolution
    reprojected_profile = reproject_profile_to_new_crs(src_profile, dst_crs, target_resolution=tr)
    resampling = Resampling[resampling]
    if preserve_rank and src_array.ndim == 2:
        reprojected_profile['count'] = 1
        dst_shape = (reprojected_profile['height'], reprojected_profile['width'])
    else:
        dst_shape = (reprojected_profile['count'], reprojected_profile['height'], reprojected_profile['width'])
    dst_array = np.zeros(dst_shape, dtype=src_profile['dtype'])

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


def _aligned_target(
    transform: Affine, width: int, height: int, resolution: float | int | tuple
) -> tuple[Affine, int, int]:
    """Align target to specified resolution; ensures same origin.

    Source: https://github.com/rasterio/rasterio/blob/master/rasterio/warp.py#L354-L393.

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


def update_profile_resolution(src_profile: dict, resolution: float | tuple[float]) -> dict:
    transform = src_profile['transform']
    width = src_profile['width']
    height = src_profile['height']

    dst_transform, dst_width, dst_height = _aligned_target(transform, width, height, resolution)

    dst_profile = src_profile.copy()
    dst_profile['width'] = dst_width
    dst_profile['height'] = dst_height
    dst_profile['transform'] = dst_transform

    return dst_profile
