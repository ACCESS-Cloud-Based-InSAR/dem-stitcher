from shapely.affinity import translate
from shapely.geometry import box

from .exceptions import DoubleDatelineCrossing, Incorrect4326Bounds


def check_4326_bounds(bounds: list) -> bool:

    xmin, ymin, xmax, ymax = bounds

    if (xmin > xmax) or (ymin > ymax):
        raise Incorrect4326Bounds('Ensure xmin <= xmax and ymin <= ymax')

    standard_4326_box = box(-180, -90, 180, 90)
    bounds_box = box(*bounds)

    if not (standard_4326_box.intersects(bounds_box)):
        raise Incorrect4326Bounds('Make sure bounds have intersection over standard 4326 CRS i.e. '
                                  'between longitude -180 and 180 and latitude -90 and 90.')

    if (ymin < -90) or (ymax > 90):
        raise Incorrect4326Bounds('Boxes beyond the North/South Pole at +/- 90 Latitude not supported')

    return True


def get_dateline_crossing(bounds: list) -> int:
    """Checks dateline (aka antimeridian) crossing. Returns +/- 180 depending on extents of bounding box provided.
    Assumes only 1 dateline can be crossed otherwise exception raised.

    Parameters
    ----------
    bounds : list
        xmin, ymin, xmax, ymax in EPSG:4326

    Returns
    -------
    int
       0 if no dateline crossing, and +/- 180 if there is depending on sign of dateline that is intersected

    Raises
    ------
    DoubleDatelineCrossing
        If dateline is crossed twice
    Incorrect4326Bounds
        If there is no intersection with normal lat/long CRS extent i.e. longitude between -180 and 180 and latitude
        between -90 and 90.
    """
    xmin, _, xmax, _ = bounds

    check_4326_bounds(bounds)

    # This logic assumes there is intersection within the standard 4326 CRS.
    # There are exactly 2 * 2 = 4 conditions
    if (xmin > -180) and (xmax < 180):
        return 0

    elif (xmin <= -180) and (xmax < 180):
        return -180

    elif (xmin > -180) and (xmax >= 180):
        return 180

    elif (xmin <= -180) and (xmax >= 180):
        raise DoubleDatelineCrossing('Shrink your bounding area')


def split_extent_across_dateline(extent: list) -> tuple[list]:
    """If extent crosses the dateline, then we return tuple of left and right hemispheres
    assuming lat/lon CRS. Otherwise, just returns, extent and empty list

    Parameters
    ----------
    extent : list
        minx, miny, maxx, maxy

    Returns
    -------
    Tuple[List]
        (bounds_of_extent_on_left_hemisphere,
         bounds_of_extent_on_right_hemisphere) if corsses dateline

         Otherwise,
         (extent, [])
    """
    crossing = get_dateline_crossing(extent)

    if crossing:
        left_hemisphere = box(-180, -90, 0, 90)
        right_hemisphere = box(0, -90, 180, 90)

        extent_box = box(*extent)
        translation_x = - crossing * 2

        extent_box_t = translate(extent_box, translation_x, 0)
        multipolygon = extent_box.union(extent_box_t)

        bounds_l = list(multipolygon.intersection(left_hemisphere).bounds)
        bounds_r = list(multipolygon.intersection(right_hemisphere).bounds)
        return (bounds_l, bounds_r)

    else:
        return extent, []
