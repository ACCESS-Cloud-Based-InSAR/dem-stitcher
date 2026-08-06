# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.6.0] - 2026-08-05

### Added
* Support for the NISAR DEM v1.2 (`nisar_dem`) - the Copernicus GLO-30 (2023_1) re-referenced to the WGS84 ellipsoid by JPL and hosted in the NASA Earthdata cloud ([docs](https://nisar-docs.asf.alaska.edu/nisar-dem/)). Only the `epsg:4326` tile set is cataloged (64,800 global 1 x 1 degree COG tiles enumerated from the nested source VRTs). Tiles are read directly as COGs; Earthdata credentials in `~/.netrc` are required and `earthdata_gdal_env` provides a `rasterio.Env` with the GDAL netrc/cookie options for the Earthdata cloud redirect.
* `stitch_dem` raises a `ValueError` for `nisar_dem` when `dst_ellipsoidal_height=False` or when a `geoid_path` is supplied, since the geoid has already been removed from that DEM.
* Support for `srtm_v3` and `nasadem` restored; tile urls now point to the LP DAAC Earthdata Cloud archive (`https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/...`), which replaced the retired `e4ftl01.cr.usgs.gov` hosting (see Issue #138 and this [Earthdata forum thread](https://forum.earthdata.nasa.gov/viewtopic.php?p=25179)). Earthdata credentials in `~/.netrc` are still required.
* `pyarrow` as a runtime dependency for reading the geoparquet tile tables.
* An integration test verifying the default `egm_08` geoid on the ARIA S3 bucket is identical (registration and values) to the Agisoft upstream NGA EGM2008 1 arcminute grid it was copied from; the upstream differs only in metadata labels (EPSG:4979/`Point` vs EPSG:4326/`Area`), which the stitcher ignores.

### Fixed
* The geoid translation applied for `dst_area_or_point='Point'` was expressed in *geoid* pixels rather than *DEM* pixels, displacing the sampled geoid by ~30 arcseconds (half a geoid pixel) and biasing ellipsoidal heights by up to several centimeters wherever the geoid has a gradient (see #151). Geoid removal is now performed on the *native* DEM grid before any `Area`/`Point` relabeling, so the geoid is always interpolated where the DEM samples physically are and no geoid translation exists at all; `dst_area_or_point` becomes a pure half-pixel relabeling of the output transform that never changes the height samples. The golden test datasets with ellipsoidal heights were regenerated (they moved by up to ~3 cm).

### Changed
* `dst_area_or_point` now accepts `None` and defaults to it (**breaking**, previously `'Area'`) in `stitch_dem` and `merge_and_transform_dem_tiles`: `None` inherits the source DEM's registration, so the default output stays on the native grid of the source tiles - `'Point'` for every supported DEM except `3dep` (`'Area'`) - and matches the NISAR DEM exactly in georeferencing for `glo_30`. Passing `'Area'` or `'Point'` explicitly relabels the output transform by half a pixel; since geoid removal precedes the relabeling, this changes only the output transform/tag, never the height samples.
* The geoid is no longer assumed to be in `epsg:4326`: `read_geoid` gains an `extent_crs` argument and `remove_geoid` passes the DEM profile's CRS through, so geoid grids in any geographic CRS (e.g. `geoid_18` in EPSG:6318 / NAD83(2011)) are windowed and resampled through their own CRS. Note `geoid_18` remains a hybrid NAVD88 geoid: using it in place of EGM2008 moves a stitched `glo_30` ~9 cm away from the NISAR DEM, so it is not a path to closer NISAR agreement.
* `remove_geoid` no longer takes `dem_area_or_point` (**breaking**): it interpolates the geoid at the sample locations implied by the given profile's transform and must be applied before pixel-registration relabeling. It gains a `resampling` argument that defaults to `'cubic'` (previously hard-coded `'bilinear'`), which empirically halves the residual against JPL's independently interpolated EGM2008. Stitched `glo_30` with ellipsoidal heights now agrees with the NISAR DEM to ~1 mm (std) in a Los Angeles test area and to ~0.25 mm over sampled high-latitude tiles, verified by a new integration test over randomly selected (seeded) tiles.
* Tile tables migrated from `*.geojson.zip` (gzipped GeoJSON) to geoparquet (`*.parquet` with `zstd` compression); `datasets.py` reads them with `gpd.read_parquet`. The `geojson_io` module remains available.
* The `organize_tile_data` notebooks write geoparquet and form the new LP DAAC cloud urls.


## [2.5.14] - 2026-08-05

### Changed
* Environment management migrated from conda/mamba to [pixi](https://pixi.sh); all configuration lives under `[tool.pixi.*]` in `pyproject.toml` and `pixi.lock` is committed.
* Minimum supported python raised from 3.9 to 3.10; CI matrix now runs the `py310`-`py313` pixi environments via `prefix-dev/setup-pixi`.
* `flake8` and its plugins dropped from the develop extra in favor of `ruff`, which is exposed as the `lint`/`format`/`fix`/`format-check` pixi tasks.
* `static-analysis.yml` no longer calls the ASFHyP3 reusable ruff workflow, which set its environment up with `mamba-org/setup-micromamba` and `environment.yml`; the ruff job is inlined and runs through pixi so CI uses the same pinned `ruff` as local development. The reusable secrets-analysis workflow is unchanged.
* Type hints modernized to PEP 604 unions (`X | Y`) now that python 3.10 is the floor.

### Fixed
* `test_mask_differences_with_merge_nodata_values_with_ellipsoidal` compared `float32` geoid values at `decimal=6`, which is below `float32` resolution at those magnitudes; it now uses `assert_allclose` with a `1e-6` relative tolerance so single-ULP differences across GDAL builds do not fail the suite.

### Removed
* `environment.yml` - superseded by the pixi manifest in `pyproject.toml`.
* The `python -m pip install --no-deps .` step in `test.yml` - `dem_stitcher` is registered under `[tool.pixi.pypi-dependencies]` as an editable install, so `pixi install` already puts it in every environment.


## [2.5.13] - 2026-02-09

### Removed
* Support for `srtm_v3` on account of lpdaac is no longer hosting the tiles (see Issue linked below). When new urls are added, we will include this.
  * https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/138


## [2.5.12] - 2025-01-29

## Fixed
* Ruff linting and formatting
* In-memory merge of files - preserving nodata and dtypes correctly

## Added
* Tests for in-memory merge
* Tests for crop profile
* Allows users to specify `dst_tile_dir` for location of tiles
* Allows users to specify `overwrite_existing_tiles` for overwriting existing tiles (should tiles need to be re-used in the same directory)

## Removed
* Dependency of environment.yml on anaconda and default distributions (now only `conda-forge`). This is purely ascethetic as the package's highest priority channel is `conda-forge`.


## [2.5.11]

## Fixed
* Python 3.13 compatibility (was not listed properly in pyproject.toml)


## [2.5.10]

## Fixed
* 3.9 compatibility due to 3.10+ type hints.
* Adds 3.13 compatibility.
* Fixes the github action for tests to correctly use python versions specified by the matrix

## Changed
* Removes `|` in type hints for 3.9 compatibility.

## [2.5.9]

## Added
* Uses ruff exclusively for linting and formatting following OPERA/ARIA linting standards from DIST-S1.
* Added `geoid_path` to `stitch_dem` to allow for user to specify geoid path. If None, then default geoid is used.
* Added UserWarning when geoid file does not cover the dateline.

## Changed
* Updated `geoid.py` to use the new geoid path for egm08 with 1 arc-second resolution.
* Library is in `src` directory per: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
  * Helps with Ruff, too.

### Fixed
* Allows users to bring their own geoid data as noted [here](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/100). 
* Ruff linting and docstring issues using the new ruff configuration
* Updates test action workflow with micromamba action.

### Removed
* Removed explicit flake8 action (should be handled by ruff).

## [2.5.8]
### Fixed
* Resolves read_geoid issue [here](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/96).
  * Update geoid url for egm08 (again) creating public bucket for ACCESS processing
  * Included egm96 as gtx in the data directory
  * egm08 and egm96 data comes from here: https://download.osgeo.org/proj/vdatum/

## [2.5.7]

### Fixed
* Check for Earthdata credentials in netrc (adapted from Joe Kennedy/Forrest Williams) resolving isse [#83](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/83)
  * when no credentials in netrc are present when requesting data for `nasadem` or `srtm_v3`, there is a human readable error instructing user to update their `~/.netrc`.
* Updates some ruff linting
  * Ensures ruff in `environment.yml`
  * Ensure single quotes for consistency.
### Changed
* egm08 is now using 2.5 deg raster rather than 1 deg.


## [2.5.6]
* Updated URLs for downloading geoids from agisoft.com. Fixes [#88](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/88).

## [2.5.5]
* Multithreading for windowed reading during merge operation
* Add 3.12 support
* Introduce ruffformatting - i.e. add ruff workflow to actions for static analysis and reformat python files.
* Provide separate progress bar for opening dataset, reading tile metadata, and reading tile array.
* Supresses: `RuntimeWarning: invalid value encountered in intersection` from `shapely`

## [2.5.4]
* Fix urls found in pyproject.toml so they correctly link on PyPI

## [2.5.3]
* Updated license in pyproject.toml that was causing pypi to reject upload


## [2.5.2]
Not on PyPI

## Changed
* Updated environment.yml and pyproject.toml for modern build of wheels
* Updated github actions to tie to specific version of ASF resuable workflows
* Included dependabot.yml


## [2.5.1]

Not on PyPI

## Changed
* Update `merge_tile_datasets_within_extent` (formely named `merged_tile_datasets`) to only read data within provided extents
    * Requires `extent` (i.e. `list[float]`) as input now.
* Internally, swap use of m x n arrays (with total dimensions 2) to the 3 dimensional arrays c x m x n. Specifically, use 
band interleaved by pixel (BIP) format where c is the number of channels. Although the API remains
unchanged (outputs 2 dimensional array), the intermediate functions are slightly more general and applicable.
  * merged.py - all functions now accept BIP (3d arrays) and return them
  * geoid.py - all functions return and expect BIP (3d arrays) including the input dem array.
* Improved performance of merge by reading only the extent that is required.
* Typing for 3.9+
* Use pyproject.toml for installation.

### Added
* Support for 1/3 arc second 3Dep
* Tests using golden datasets and mocked tiles/geoid - ensures correctness of transformations

### Removed
* Support for NED1 and 3Dep 1 arcsecond
* Support for Python 3.7 and 3.8
* setup.py

## [2.5.0]

### Added
- The function `get_dem_tile_paths` to extract urls or local paths to dem tiles specifying bounds and dem names.
- Notebook illustrating how to create a `vrt` file using `get_dem_tile_paths`.
- Utilizes `get_dem_tile_paths` in main `stitch_dem` for easier testing.
- Caches dem tile extents loaded from compressed geojson.

## Removed
- `driver` keyword in `stitch_dem`.

## [2.4.0]

### Added
- Included feature for extracting DEMs across datelines
- Updated merge apis with more descriptive names for more general usage
- Exceptions to determine valid extents and ensure single dateline crossing
- Added functions for dateline in `dateline.py`
- Tests for added and changed functionality.
- Integration tests for notebooks.
- Clarity about driver keyword in `stitch_dem` in readme, docstrings
- Ensure overlap of tiles is non-trivial AND polygonal (excludes point and line intersections)
- Similar check of polygonal type for window reading for better error handling
- Add `merge_nodata_value` to `merge_tile_datasets`, `merge_and_transform_dem_tiles`, and `stitch_dem` to allow for fill value of 0. As such, nodata areas within DEM tiles when converted to Ellipsoidal height will be filled in with geoid values. No other values outside of `np.nan` or `0` permitted.


### Changed
- Moved functions into more logical python file including merge calls into `merge.py` and tile functions into `datasets.py`
- Renamed internal functions for greater clarity and better description of tasks
- Ensures window reading checks bounds of src raster and does intersection if required to ensure no unexpected rasterio errors. Further, raises error if no overlap.


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
