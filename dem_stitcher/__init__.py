import warnings

# FIXME: Python 3.8+ this should be `from importlib.metadata...`
from importlib_metadata import PackageNotFoundError, version

from .datasets import get_global_dem_tile_extents, get_overlapping_dem_tiles
from .stitcher import get_dem_tile_paths, stitch_dem

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = None
    warnings.warn('package is not installed!\n'
                  'Install in editable/develop mode via (from the top of this repo):\n'
                  '   python -m pip install -e .\n', RuntimeWarning)


__all__ = [
    'get_dem_tile_paths',
    'get_global_dem_tile_extents',
    'get_overlapping_dem_tiles',
    'stitch_dem',
    '__version__',
]
