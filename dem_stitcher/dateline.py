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
