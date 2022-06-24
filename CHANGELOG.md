# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0]

### Added
- Added `dst_resolution` to specify resolution of output DEM; does not alter origin; can be used to enforce square dimensions if desired
- Added tests for `rio_window.py`, `stitcher.py`, `geoid.py`, and `rio_tools.py`; including integration test which is marked
- Added notebooks related to issues #31 and #32

### Changed
- Returned API to original form such that `stitch` returns tuple: `(dem_array, dem_metadata_dictionary)`
- Github actions now run on tests that are not "integration" tests, so no internet connectivity required
- Function `remove_geoid` updated to use non-resampling windowing and warns user if user does not properly set resolution buffer
- Removed gdal python bindings unrelated to rasterio
- Updated ISCE notebook

### Fixed
- Fix issues #31 and #32: resampling/translation bug - do not resample unless specified in `dst_resolution`

## [2.1.1]

## Changed
* `dem_sticher` can now be installed in a Python 3.7 environment. Support for Python 3.7
  is unlikely to remain long term as most upstream packages have dropped support for it
  and [Python 3.7 End Of Life](https://endoflife.date/python) is slated for 27 Jun 2023.
* update installation instructions for consistency vis-a-vis other repos

## [2.1.0]

### Changed
* `dem_sticher.sticher.stitch_dem` no longer returns the raster profile and data
  array and instead writes the output stitched DEM to a file as specified by the
  new `filepath` argument.

### Fixed
* Pixel shifts sometimes seen in stitched output DEMs (see [#18](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/pull/18))
* [Package data](dem_stitcher/data/) is again included with python wheel distributions,
  which was missing in v2.0.1
* Properly handle no-data values and geoid bounds.

## [2.0.1]

### Fixed
* Square dimensions for DEM pixels are now enforced to prevent distortion along polar regions.

## [2.0.0]

**Note: this was an accidental release when adjusting CI/CD pipelines and is the same as v1.0.0**

Initial release of `dem-stitcher`, a package for obtaining DEM rasters:
 * finalize API, CI/CD, and demos

## [1.0.0]

Initial release of `dem-stitcher`, a package for obtaining DEM rasters:
 * finalize API, CI/CD, and demos

## [0.0.1]

Beta release of `dem-stitcher`, a package for obtaining DEM rasters