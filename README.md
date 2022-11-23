# dem-stitcher

[![PyPI license](https://img.shields.io/pypi/l/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![PyPI version](https://img.shields.io/pypi/v/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![Conda version](https://img.shields.io/conda/vn/conda-forge/dem_stitcher)](https://anaconda.org/conda-forge/dem_stitcher)
[![Conda platforms](https://img.shields.io/conda/pn/conda-forge/dem_stitcher)](https://anaconda.org/conda-forge/dem_stitcher)

This tool aims to (a) provide a continuous raster of global Digital Elevation Raster over an area of interest and (b) perform some standard transformations for processing. Such transformations include:

+ converting the vertical datum from a reference geoid to the WGS84 ellipsoidal
+ ensuring a coordinate reference system centered at either the upper-left corner (`Area` tag) or center of the pixel (`Point` tag).

We utilize the GIS formats from `rasterio`. The API can be summarized as

```
# as xmin, ymin, xmax, ymax in epsg:4326
bounds = [-119.085, 33.402, -118.984, 35.435]

X, p = stitch_dem(bounds,
                  dem_name='glo_30',
                  dst_ellipsoidal_height=False,
                  dst_area_or_point='Point')
# X is an m x n numpy array
# p is a dictionary (or a rasterio profile) including relevant GIS metadata
```
Then, to save the DEM:
```
import rasterio

with rasterio.open('dem.tif', 'w', **p) as ds:
   ds.write(X, 1)
   ds.update_tags(AREA_OR_POINT='Point')
```
Global DEMs supported are tiled in lat/lon (`epsg:4326`) and the API assumes that bounds are supplied in this format.

# Installation

In order to easily manage dependencies, we recommend using dedicated project environments
via [Anaconda/Miniconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html).
or [Python virtual environments](https://docs.python.org/3/tutorial/venv.html).

`dem_stitcher` can be installed into a conda environment with

```
conda install -c conda-forge dem_stitcher
```

or into a virtual environment with

```
python -m pip install dem_stitcher
```

Currently, python 3.7+ is supported.

## With ISCE2 or gdal

Although the thrust of using this package is for staging DEMs for InSAR (particularly ISCE2), testing and maintaining suitable environments to use with InSAR processors is beyond the scope of what we are attempting to accomplish here. We provide an example notebook [here](./notebooks/Staging_a_DEM_for_ISCE2.ipynb) that demonstrates how to stage a DEM for ISCE2, which requires additional packages than required for the package on its own and additionally requires python version `<3.10`. For the notebook, we use the environment found in `environment.yml` of the Dockerized TopsApp [repository](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/environment.yml), used to generate interferograms (GUNWs) in the cloud.

## Credentials

The accessing of NASADEM and SRTM require earthdata login credentials to be put into the `~/.netrc` file. If these are not present, the stitcher will
fail with `BadZipFile Error` as we use `requests` to obtain zipped data and load the data using `rasterio`. An entry in the `.netrc` will look like:

```
machine urs.earthdata.nasa.gov
    login <username>
    password <password>
```

# Notebooks

We have notebooks to demonstrate common usage:

+ [Basic Demo](notebooks/Basic_Demo.ipynb)
+ [Comparing DEMs](notebooks/Comparing_DEMs.ipynb)
+ [Staging a DEM for ISCE2](notebooks/Staging_a_DEM_for_ISCE2.ipynb) - this notebook requires the installation of a few extra libraries including ISCE2 via `conda-forge`

We also demonstrate how the tiles used to organize the urls for the DEMs were generated for this tool were generated in this [notebook](notebooks/organize_tile_data/).

# DEMs Supported

The [DEMs](https://github.com/ACCESS-Cloud-Based-InSAR/dem_stitcher/tree/main/dem_stitcher/data) that can currently be used with this tool are:

```
In [1]: from dem_stitcher.datasets import DATASETS; DATASETS
Out[1]: ['srtm_v3', 'nasadem', 'glo_90_missing', 'glo_30', '3dep', 'glo_90', 'ned1']
```

All the tiles are given in lat/lon CRS (i.e. `epsg:4326`). A notable omission is the Artic DEM [here](https://www.pgc.umn.edu/data/arcticdem/), which is suitable for DEMs at the northern pole of the globe due to lat/lon distortion.

1. `glo_30`/`glo_90`: Copernicus GLO-30/GLO-90 DEM. They are the 30 and 90 meter resolution, respectively [[link](https://registry.opendata.aws/copernicus-dem/)].
2. The USGS DEMSs:
   - `ned1`:  Ned 1 arc-second (deprecated by USGS) [[link](https://cugir.library.cornell.edu/catalog/cugir-009096)]
   - `3dep`: 3Dep 1 arc-second[[link](https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1)]
3. `srtm_v3`: SRTM v3 [[link](https://dwtkns.com/srtm30m/)]
4. `nasadem`: Nasadem [[link](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)]
5. `glo_90_missing`: these are tiles that are in `glo_90` but not in `glo_30`. They are over the countries Armenia and Azerbaijan. Used internally to help fill in gaps in coverage of `glo_30`.

If there are issues with obtaining dem tiles from urls embedded within the geojson tiles (e.g. a `404` error as [here](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/48)), please see the [Development](#for-development) section below and/or open an issue ticket.

# DEM Transformations

Wherever possible, we do not resample the original DEMs unless specified by the user to do so. When extents are specified, we obtain the the minimum  pixel extent within the merged tile DEMs that contain that extent. Any required resampling (e.g. updating the CRS or updating the resolution because the tiles have non-square resolution at high latitudes) is done after these required translations. We importantly note that order in which these transformations are done is crucial, i.e. first translating the DEM (to either pixel- or area-center coordinates) and then resampling is different than first resampling and then translation (as affine transformations are not commutative). Here are some notes/discussions:

1. All DEMs are resampled to `epsg:4326` (most DEMs are in this CRS except some of the USGS DEMs, which are in `epsg:4269` and is an almost identical CRS over North America).
2. All DEM outputs will have origin and pixel spacing aligning with the original DEM tiles unless a resolution for the final product is specified, which will alter the pixel spacing.
3. Georeferenced rasters can be tied to map coordintaes using either (a) upper-left corners of pixels or (b) the pixel centers i.e. `Point` and `Area` tags in `gdal`, respectively, and seen as `{'AREA_OR_POINT: 'Point'}`. Note that tying a pixel to the upper-left cortner (i.e. `Area` tag) is the *default* pixel reference for `gdal` as indicated [here](https://gdal.org/tutorials/geotransforms_tut.html). Some helpful resources in reference to DEMs about this book-keeping are below.
   + SRTM v3, NASADEM, and TDX are [Pixel-centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904), i.e. `{'AREA_OR_POINT: 'Point'}`.
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects), i.e. `{'AREA_OR_POINT: 'Area'}`.
4. Transform geoid heights to WGS84 Ellipsoidal height. This is done using the rasters [here](https://www.agisoft.com/downloads/geoids/). We:
   + Adjust the geoid to pixel/area coordinates
   + resample the geoids into the DEM reference frame
   + Adjust the vertical datum
5. All DEMs are converted to `float32` and have nodata `np.nan`. Although this can increase data size of certain rasters (SRTM is distributed as integers), this ensures (a) easy comparison across DEMs and (b) no side-effects of the stitcher due to unusual nodata values. Note, this datatype is done in `merge_tiles` in the `stitcher.py`. Other nodata values can be specified outside the stitcher as is frequently done (e.g. ISCE2 requires nodata to be filled as `0`).

There are some [notebooks](notebooks/analysis_and_comparison) that illustrate how tiles are merged by comparing the output of our stitcher with the original tiles.

As a performance note, when merging DEM tiles, we merge the all needed tiles in memory and this process has an associated overhead. An alternative approach would be to download the tiles to disk and use virtual warping. Ultimately, the accuracy of the final DEM is our prime focus and these minor performance tradeoffs are sidelined.

# Dateline support

We assume that the supplied bounds overlap the standard lat/lon CRS grid i.e.longitudes between -/+ 180 longitude and within -/+ 90 latitude. If there is a dateline crossing by the supplied bounds, then the tiles are wrapped and translated to provide a continuous raster over the area provided. No wrapping around poles (i.e. at -/+ 90 latitude) is supported.

# For Development

This is almost identical to normal installation:

1. Clone this repo `git clone https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher.git`
2. Navigate with your terminal to the repo.
3. Create a new environment and install requirements using `conda env update --file environment.yml` (or use [`mamba`](https://github.com/mamba-org/mamba) to speed the install up)
4. Install the package from cloned repo using `python -m pip install -e .`

## DEM Urls

If urls or readers need to be updated (they consistently do) or you want to add a new global or large DEM, then there are two points of contact:

1. The notebooks that format the geojsons used for this library are [here](notebooks/organize_tile_data/)
2. The readers are [here](dem_stitcher/dem_readers.py)

The former is the more likely. When re-generating tiles, make sure to run all tests including integration tests (i.e. `pytest tests`). For example, if regenerating `glo` tiles, `glo-30` requires both resolution parameters (30 meters and 90 meters) and an additional notebook for filling in missing 30 meter tiles. These should be clearly spelled out in the notebook linked above.

# Testing

1. Install `pytest`
2. Run `pytest .`

 We have an integration test (marked as `integration`) which ensures all the datasets are downloaded and can be transformed (not validated for correctness at this time). Otherwise, all tests have basic tests with mock data to illustrate how the DEM stitcher is working. The non-integration tests are as github actions via `pytest tests -m "not integration"`.

# Contributing

We welcome contributions to this open-source package. To do so:

1. Create an GitHub issue ticket desrcribing what changes you need (e.g. issue-1)
2. Fork this repo
3. Make your modifications in your own fork
4. Make a pull-request in this repo with the code in your fork and tag the repo owner or a relevant contributor.

We use `flake8` and associated linting packages to ensure some basic code quality (see the `environment.yml`). These will be checked upon pull request.

# Support

1. Create an GitHub issue ticket desrcribing what changes you would like to see or to report a bug.
2. We will work on solving this issue (hopefully with you).

# Acknowledgements

This tool was developed to support cloud SAR processing using ISCE2 and various research. The early work of this repository was done by Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard. Since the utilization of this package for GUNW generation (see this [repo](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp)), a subset of the ACCESS team, including Joseph (Joe) H. Kennedy, Simran Sangha, Grace Bato, Andrew Johnston, and Charlie Marshak, have improved this repository greatly. In particular, Joe Kennedy has lead the inclusion/development of actions, tests, packaging, distribution (including PyPI and `conda-forge`) and all the things to make this package more reliable, accessible, readable, etc. Simran Sangha has helped make sure output rasters are compatible with ISCE2 and other important bug-fixes.
