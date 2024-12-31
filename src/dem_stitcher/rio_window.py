import math
import warnings
from warnings import warn

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import array_bounds, rowcol, xy
from rasterio.windows import Window
from shapely.geometry import box


def get_cropped_profile(profile: dict, slice_x: slice, slice_y: slice) -> dict:
    """Return a cropped profile from a reference profile and numpy slices.

    Return a cropped profile from a reference profile and numpy slices (i.e.
    np.s_[start: stop]) to create a new profile that is within the window of
    slice_x, slice_y.

    Parameters
    ----------
    profile : dict
        The reference rasterio profile.
    slice_x : slice
        The horizontal slice.
    slice_y : slice
        The vertical slice.

    Returns
    -------
    dict:
        The rasterio dictionary from cropping.
    """
    x_start = slice_x.start or 0
    y_start = slice_y.start or 0
    x_stop = slice_x.stop or profile['width']
    y_stop = slice_y.stop or profile['height']

    if (x_start < 0) | (x_stop < 0) | (y_start < 0) | (y_stop < 0):
        raise ValueError('Slices must be positive')

    width = x_stop - x_start
    height = y_stop - y_start

    profile_cropped = profile.copy()

    trans = profile['transform']
    x_cropped, y_cropped = xy(trans, y_start, x_start, offset='ul')
    trans_list = list(trans.to_gdal())
    trans_list[0] = x_cropped
    trans_list[3] = y_cropped
    tranform_cropped = Affine.from_gdal(*trans_list)
    profile_cropped['transform'] = tranform_cropped

    profile_cropped['height'] = height
    profile_cropped['width'] = width

    return profile_cropped


def get_array_bounds(profile: dict) -> list[float]:
    return array_bounds(profile['height'], profile['width'], profile['transform'])


def transform_bounds(src_bounds: list, src_crs: CRS, dest_crs: CRS) -> list[float]:
    """Source: https://gis.stackexchange.com/a/392407."""
    proj = Transformer.from_crs(src_crs, dest_crs, always_xy=True)

    bl = proj.transform(src_bounds[0], src_bounds[1])
    tr = proj.transform(src_bounds[2], src_bounds[3])
    dest_bounds = list(bl) + list(tr)

    return dest_bounds


def get_indices_from_extent(
    transform: Affine, extent: list[float], shape: tuple = None, res_buffer: int = 0
) -> tuple[tuple]:
    """Obtain upper left corner and bottom right corner from extents.

    Use a geo-transform that specifies resolution and upper left corner of a
    coordinate system.

    Parameters
    ----------
    transform : Affine
        Affine geo transform
    extent : List[float]
        (xmin, ymin, xmax, ymax) in the CRS of transform
    shape : tuple, optional
        Will bound the indices by (height, width), by default None
    res_buffer : int, optional
        Additional resolution buffer, by default 0

    Returns
    -------
    Tuple[tuple]
        (Coordinates of upper left corner, Coordinates of bottom right corner) where
        coordinates are (row, col) coordinates

    Notes
    -----
    Can use to slice geo-reference arrays based on extents
    """
    xmin, ymin, xmax, ymax = extent
    row_ul, col_ll = rowcol(transform, xmin, ymax, op=math.floor)
    row_br, col_br = rowcol(transform, xmax, ymin, op=math.ceil)

    corner_ul = (max(row_ul - res_buffer, 0), max(col_ll - res_buffer, 0))

    height, width = (np.inf, np.inf)
    if shape is not None:
        assert len(shape) in [2, 3]
        height, width = shape[-2:]

    corner_br = (min(row_br + res_buffer, height), min(col_br + res_buffer, width))

    return corner_ul, corner_br


def get_window_from_extent(
    src_profile: dict, window_extent: list[float], window_crs: CRS = CRS.from_epsg(4326), res_buffer: int = 0
) -> Window:
    src_shape = src_profile['height'], src_profile['width']
    src_bounds = get_array_bounds(src_profile)
    window_extent_r = transform_bounds(window_extent, window_crs, src_profile['crs'])

    src_bbox_geo = box(*src_bounds)
    win_bbox_geo = box(*window_extent_r)

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        intersection_geo = src_bbox_geo.intersection(win_bbox_geo)

    if intersection_geo.geom_type != 'Polygon':
        raise RuntimeError(
            'The intersection geometry is degenerate (i.e. a ' f'Point or LineString: {intersection_geo.geom_type}'
        )
    if not intersection_geo.is_empty:
        window_extent_r = intersection_geo.bounds
        if not src_bbox_geo.contains(win_bbox_geo):
            warn(
                f'Requesting extent beyond raster bounds of {list(src_bounds)}'
                f'. Shrinking bounds in raster crs to {window_extent_r}.',
                category=RuntimeWarning,
            )
    else:
        raise RuntimeError('The extent you specified does not overlap' ' the specified raster as a Polygon.')

    corner_ul, corner_br = get_indices_from_extent(
        src_profile['transform'], window_extent_r, shape=src_shape, res_buffer=res_buffer
    )
    row_start, col_start = corner_ul
    row_stop, col_stop = corner_br
    window = Window.from_slices((row_start, row_stop), (col_start, col_stop))
    return window


def format_window_profile(src_profile: dict, window_arr: np.ndarray, window_transform: Affine) -> dict:
    profile_window = src_profile.copy()
    profile_window['transform'] = window_transform

    profile_window['count'] = window_arr.shape[0]
    profile_window['height'] = window_arr.shape[1]
    profile_window['width'] = window_arr.shape[2]
    return profile_window


def read_raster_from_window(
    raster_path: str, window_extent: list, window_crs: CRS = CRS.from_epsg(4326), res_buffer: int = 0
) -> tuple:
    """Obtain minimum pixels from original raster (specified by raster_path) that contains window extent.

    This does not reproject into window extent! Returns only 1st channel.

    Parameters
    ----------
    raster_path : str
        Path or url to raster
    window_extent : list
        (xmin, ymin, xmax, ymax) in specified CRS
    window_crs : CRS
        CRS of window extent
    res_buffer : int, optional
        Additional pixel buffer in raster_path resolution, by default 0.
        Note that we specify box by pixel that contains upper left corner and
        lower right corner.

    Returns
    -------
    tuple
        (array, profile) where profile is rasterio profile and array is the first channel of the image

    Raises
    ------
    ValueError
       Extent is not properly specified
    """
    if (window_extent[0] >= window_extent[2]) or (window_extent[1] >= window_extent[3]):
        raise ValueError('Extents must be in the form of (xmin, ymin, xmax, ymax)')

    with rasterio.open(raster_path) as ds:
        src_profile = ds.profile

    window = get_window_from_extent(src_profile, window_extent, window_crs, res_buffer=res_buffer)

    with rasterio.open(raster_path) as ds:
        arr_window = ds.read(window=window)
        t_window = ds.window_transform(window)

    profile_window = format_window_profile(src_profile, arr_window, t_window)

    return arr_window, profile_window
