from rasterio.windows import transform as get_window_transform
from rasterio.windows import from_bounds as window_from_bounds
import rasterio
from pyproj import Transformer
from rasterio.crs import CRS


def get_window_profile(window, window_transform, ref_profile):
    profile = ref_profile.copy()
    profile['transform'] = window_transform
    profile['width'] = int(window.width)
    profile['height'] = int(window.height)
    profile['crs'] = ref_profile['crs']
    profile['count'] = 1
    profile['nodata'] = None
    return profile


def get_bounds_buffer(bounds: list, buffer=.05) -> list:
    xmin, ymin, xmax, ymax = bounds
    width = xmax - xmin
    height = ymax - ymin
    buffer_length = min(width, height) * buffer
    return (xmin - buffer_length,
            ymin - buffer_length,
            xmax + buffer_length,
            ymax + buffer_length
            )


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


def read_raster_from_window(raster_path: str,
                            window_bounds: list,
                            window_crs: CRS,
                            buffer: float = .05) -> tuple:
    """
    Get subset of large GIS raster.

    Assume single channel
    """
    with rasterio.open(raster_path) as ds:
        src_profile = ds.profile
        src_crs = ds.crs

    w_bounds_src = list(window_bounds)
    if window_crs != src_crs:
        w_bounds_src = transform_bounds(window_bounds, window_crs, src_crs)

    w_bounds_src = get_bounds_buffer(w_bounds_src, buffer)

    window = window_from_bounds(*w_bounds_src,
                                transform=src_profile['transform'])
    window_transform = get_window_transform(window,
                                            src_profile['transform'])

    with rasterio.open(raster_path) as ds:
        window_arr = ds.read(1, window=window)

    window_profile = get_window_profile(window,
                                        window_transform,
                                        src_profile)
    return window_arr, window_profile


def read_raster_from_window_geoid_18(raster_path: str,
                                     window_bounds: list,
                                     window_crs: CRS,
                                     buffer: float = .05) -> tuple:

    assert(window_crs == CRS.from_epsg(4326))
    minx, miny, maxx, maxy = window_bounds
    minx += 360
    maxx += 360

    X, p = read_raster_from_window(raster_path,
                                   window_bounds,
                                   window_crs,
                                   buffer=buffer)
    t = p['transform']

    # To ensure that we have -180 to 180 bounds
    # Note compositional order is important here and we want to translate after
    # the original transformation so comes first
    p['transform'] = t.translation(-360, 0) * t

    return X, p
