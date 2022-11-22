# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.1]

### Fixed
- Fixed tile urls for `glo*` and `srtm_v3`.
- Include directions in readme for future dem tile updates.
- Support python 3.11


## [2.3.0]

### Added
- Included Copernicus GLO-90 (as `glo_90`) and the missing GLO-30 tiles that are available as GLO-90 tiles as `glo_90_missing`
- Demonstration on how to fill in `glo-30` tiles that are missing with `glo-90` tiles.
- Exceptions that catch: a) no available tiles of specifed DEM as a `NoDEMCoverage` exception, b) badly specified `dem_name` as a `DEMNotSupported` exception and c) extent/bounds not of the form `xmin, ymin, xmax, ymax` as a `ValueError`
- API keyword argument `fill_in_glo_30` to fill in `glo_30` tiles that are missing, but whose corresponding `glo_90` tiles are not.
- Tests for Exceptions and added datasets
- Python 3.10 support with matrix in actions added back.

### Changed
- Since AWS registry removed zip, the `glo_30` and `glo_90` geojsons have precisely the tiles that are available (had to traverse bucket)
- Notebooks to organize data have been updated

### Fixed
- Fixed #33 i.e. missing `glo_30` rasters over Azerbaijan and Armenia by filling in with available `glo_90`.


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