import math
from typing import List, Tuple
from warnings import warn

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import rowcol
from rasterio.windows import Window
from shapely.geometry import box


def transform_bounds(src_bounds: list,
                     src_crs: CRS,
                     dest_crs: CRS) -> list:
    """
    Source: https://gis.stackexchange.com/a/392407
    """

    proj = Transformer.from_crs(src_crs, dest_crs, always_xy=True)

    bl = proj.transform(src_bounds[0],
                        src_bounds[1])
    tr = proj.transform(src_bounds[2],
                        src_bounds[3])
    dest_bounds = list(bl) + list(tr)

    return dest_bounds


def get_indices_from_extent(transform: Affine,
                            extent: List[float],
                            shape: tuple = None,
                            res_buffer: int = 0) -> Tuple[tuple]:
    """Obtain Upper left corner and bottom right corner from extents based on
    geo-transform that specifies resolution and upper left corner of a coordinate
    system

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

    corner_ul = (max(row_ul - res_buffer, 0),
                 max(col_ll - res_buffer, 0))

    height, width = (np.inf, np.inf)
    if shape is not None:
        height, width = shape

    corner_br = (min(row_br + res_buffer, height),
                 min(col_br + res_buffer, width))

    return corner_ul, corner_br


def read_raster_from_window(raster_path: str,
                            window_extent: list,
                            window_crs: CRS,
                            res_buffer: int = 0) -> tuple:
    """Obtains minimum pixels from original raster (specified by raster_path) that contain
    window extent. Does not reproject into window extent! Returns only 1st channel.

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
        src_crs = ds.crs
        src_bounds = list(ds.bounds)

    src_shape = src_profile['height'], src_profile['width']
    window_extent_r = transform_bounds(window_extent, window_crs, src_crs)

    src_bbox_geo = box(*src_bounds)
    win_bbox_geo = box(*window_extent_r)

    intersection_geo = src_bbox_geo.intersection(win_bbox_geo)

    if intersection_geo.geom_type != 'Polygon':
        raise RuntimeError('The intersection geometry is degenerate (i.e. a '
                           f'Point or LineString: {intersection_geo.geom_type}')
    if not intersection_geo.is_empty:
        window_extent_r = intersection_geo.bounds
        if not src_bbox_geo.contains(win_bbox_geo):
            warn(f'Requesting extent beyond raster bounds of {list(src_bounds)}'
                 f'. Shrinking bounds in raster crs to {window_extent_r}.',
                 category=RuntimeWarning)
    else:
        raise RuntimeError('The extent you specified does not overlap'
                           ' the specified raster as a Polygon.')

    corner_ul, corner_br = get_indices_from_extent(src_profile['transform'],
                                                   window_extent_r,
                                                   shape=src_shape,
                                                   res_buffer=res_buffer
                                                   )
    row_start, col_start = corner_ul
    row_stop, col_stop = corner_br
    window = Window.from_slices((row_start, row_stop),
                                (col_start, col_stop))

    with rasterio.open(raster_path) as ds:
        arr_window = ds.read(1, window=window)
        t_window = ds.window_transform(window)

    profile_window = src_profile.copy()
    profile_window['transform'] = t_window

    profile_window['height'] = arr_window.shape[0]
    profile_window['width'] = arr_window.shape[1]

    return arr_window, profile_window
