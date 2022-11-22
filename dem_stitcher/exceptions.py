class NoDEMCoverage(Exception):
    """Throw this exception if extent/bounds does not cover any available DEM tiles"""


class DEMNotSupported(Exception):
    """Throw this exception if DEM Name is not supported"""


class DoubleDatelineCrossing(Exception):
    """Throw this exception if dateline is crossed twice i.e. at longitude of -180 and 180"""


class Incorrect4326Bounds(Exception):
    """If epsg:4326 xmin, ymin, xmax, ymax does not intersect -180, -90, 180, 90"""
