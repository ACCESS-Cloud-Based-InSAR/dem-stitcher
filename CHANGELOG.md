# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0]

- Return API to original form (array, dictionary)
- Fix Issues #31 and #32: resampling/translation bug - do not resample unless specified in `dst_resolution`
- Add `dst_resolution` to specify resolution of output DEM; does not alter origin
- Add tests for `rio_window.py`, `stitcher.py`, `geoid.py`, and `rio_tools.py`; including integration test
- Added notebooks related to #31 and #32


## [1.0.0]

Initial release of `dem-stitcher`, a package for obtaining DEM rasters:
 * finalize API, CI/CD, and demos

## [0.0.1]

Beta release of `dem-stitcher`, a package for obtaining DEM rasters