# dem-stitcher

[![PyPI license](https://img.shields.io/pypi/l/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![PyPI version](https://img.shields.io/pypi/v/dem_stitcher.svg)](https://pypi.python.org/pypi/dem_stitcher/)
[![Conda version](https://img.shields.io/conda/vn/conda-forge/dem_stitcher)](https://anaconda.org/conda-forge/dem_stitcher)
[![Conda platforms](https://img.shields.io/conda/pn/conda-forge/dem_stitcher)](https://anaconda.org/conda-forge/dem_stitcher)

This tool provides a raster of a Digital Elevation Model (DEM) over an area of interest utilizing global or continental, publicly available tile sets such as the [Global Copernicus Digital Elevation Model at 30 meter resolution](https://registry.opendata.aws/copernicus-dem/). See the [Datasets](#dems-supported) section below for all the tiles supported and their shortnames. This tool also performs some standard transformations for processing such as:

+ the conversion of the vertical datum from a reference geoid to the WGS84 ellipsoidal
+ the accounting of a coordinate reference system centered at either the upper-left corner (`Area` tag) or center of the pixel (`Point` tag).

We rely on the GIS formats from `rasterio`. The API can be summarized as

```
from dem_stitcher import stitch_dem

# as xmin, ymin, xmax, ymax in epsg:4326
bounds = [-119.085, 33.402, -118.984, 35.435]

X, p = stitch_dem(bounds,
                  dem_name='glo_30',  # Global Copernicus 30 meter resolution DEM
                  dst_ellipsoidal_height=False,
                  dst_area_or_point='Point')
# X is an m x n numpy array
# p is a dictionary (or a rasterio profile) including relevant GIS metadata; CRS is epsg:4326
```
Then, to save the DEM raster to disk:
```
import rasterio

with rasterio.open('dem.tif', 'w', **p) as ds:
   ds.write(X, 1)
   ds.update_tags(AREA_OR_POINT='Point')
```
The rasters are returned in the global lat/lon projection `epsg:4326` and the API assumes that bounds are supplied in this format.

## Matching the NISAR DEM

The default keyword arguments of `stitch_dem` reproduce the [NISAR DEM](https://nisar-docs.asf.alaska.edu/nisar-dem/) from `glo_30`, i.e.

```
X, p = stitch_dem(bounds,
                  dem_name='glo_30',
                  # The defaults, spelled out
                  dst_ellipsoidal_height=True,   # remove EGM2008 
                  dst_area_or_point='Point',     # keep the native pixel-centered Copernicus grid
                  dst_resolution=None)           # keep the native tile resolution
```

agrees with `stitch_dem(bounds, dem_name='nisar_dem')` pixel-for-pixel in georeferencing and to ~1 mm in height (the residual is JPL's EGM2008 grid/interpolation vs the 1 arcminute grid used here). This is verified by an integration test over randomly selected tiles and demonstrated in this [notebook](notebooks/analysis_and_comparison/2_Comparison_with_NISAR_DEM.ipynb).

# Installation

`dem_stitcher` can be installed into a conda environment with

```
conda install -c conda-forge dem_stitcher
```

or into a virtual environment with

```
python -m pip install dem_stitcher
```

Currently, python 3.10+ is supported.

### Pixi (recommended for development)

Install [pixi](https://pixi.sh/latest/#installation), then:

```bash
git clone https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher.git
cd dem-stitcher
pixi install
pixi run python -c "import dem_stitcher; print(dem_stitcher.__version__)"
```

For JupyterLab (with `jupyter-collaboration` for real-time collaborative editing):

```bash
pixi run jupyter lab
```

The default environment uses python 3.13. Environments named `py310`, `py311`, `py312`, and
`py313` are also defined and can be selected with `pixi run -e py312 ...`.

## With ISCE2 or gdal

Although the thrust of using this package is for staging DEMs for InSAR (particularly ISCE2), testing and maintaining suitable environments to use with InSAR processors is beyond the scope of what we are attempting to accomplish here. We provide an example notebook [here](./notebooks/Staging_a_DEM_for_ISCE2.ipynb) that demonstrates how to stage a DEM for ISCE2, which requires additional packages than required for the package on its own. For the notebook, we use the environment found in `environment.yml` of the Dockerized TopsApp [repository](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/environment.yml), used to generate interferograms (GUNWs) in the cloud.

## About the raster metadata

The creation metadata unrelated to georeferencing (e.g. the `compress` key or various other options [here](https://rasterio.readthedocs.io/en/latest/topics/image_options.html#creation-options)) returned in the dictionary `profile` from the `stitch_dem` API is copied directly from the source tiles being used if they are GeoTiff formatted (such as `glo_30`) else the creation metadata are copied from the GeoTiff Default Profile in `rasterio` (see [here](https://github.com/rasterio/rasterio/blob/0feec999775f3108abf9f50beea044bb3d4756d2/rasterio/profiles.py) excluding `nodata` and `dtype`). Such metadata creation options are beyond the scope of this library.

## Credentials

The accessing of NASADEM, SRTM, and the NISAR DEM require earthdata login credentials to be put into the `~/.netrc` file. If these are not present, the stitcher will
fail with `ValueError` asking you to update the `~/.netrc`. The appropriate entry appears as:
```
machine urs.earthdata.nasa.gov
    login <username>
    password <password>
```
For `nisar_dem`, the tiles are read directly with `rasterio`/GDAL, so the stitcher opens and reads them within a `rasterio.Env` that sets `GDAL_HTTP_NETRC`, `GDAL_HTTP_COOKIEFILE`, and `GDAL_HTTP_COOKIEJAR` so GDAL can authenticate through the Earthdata cloud redirect. If you get `nisar_dem` urls from `get_dem_tile_paths` and open them yourself, use the same environment:

```python
import rasterio
from dem_stitcher.credentials import earthdata_gdal_env

with earthdata_gdal_env():
    with rasterio.open(url) as ds:
        dem_arr = ds.read(1)
```

# Notebooks

We have notebooks to demonstrate common usage:

+ [Basic Demo](notebooks/Basic_Demo.ipynb)
+ [Comparing DEMs](notebooks/Comparing_DEMs.ipynb)
+ [Generating a VRT from source DEM tiles](notebooks/Merging_DEM_Tiles_into_a_VRT.ipynb)
+ [Staging a DEM for ISCE2](notebooks/Staging_a_DEM_for_ISCE2.ipynb) - this notebook requires the installation of a few extra libraries including ISCE2 via `conda-forge`

We also demonstrate how the tiles used to organize the urls for the DEMs were generated for this tool were generated in this [notebook](notebooks/organize_tile_data/).

# DEMs Supported

The [DEMs](https://github.com/ACCESS-Cloud-Based-InSAR/dem_stitcher/tree/main/dem_stitcher/data) that are currently supported are:

```
In [1]: from dem_stitcher.datasets import DATASETS; DATASETS
Out[1]: ['3dep', 'glo_30', 'glo_90', 'glo_90_missing', 'nasadem', 'nisar_dem', 'srtm_v3']
```
The shortnames aboves are the strings required to use `stitch_dem`. Below, we expound upon these DEM shortnames and link to their respective data repositories.

1. `glo_30`/`glo_90`: Copernicus GLO-30/GLO-90 DEM. The tile sets are the 30 and 90 meter resolution, respectively [[link](https://registry.opendata.aws/copernicus-dem/)].
2. The USGS DEM `3dep`: 3Dep 1/3 arc-second over North America - we are storing the ~10 meter resolution dataset. There are many more as noted [here](https://www.usgs.gov/the-national-map-data-delivery/gis-data-download?qt-science_support_page_related_con=0#qt-science_support_page_related_con). The files for these DEMs are [here](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/)
3. `srtm_v3`: SRTM v3 [[link](https://lpdaac.usgs.gov/products/srtmgl1v003/)] - tiles are downloaded from the LP DAAC Earthdata Cloud archive and require Earthdata credentials in `~/.netrc` (see [Credentials](#credentials))
4. `nasadem`: Nasadem [[link](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)] - tiles are downloaded from the LP DAAC Earthdata Cloud archive and require Earthdata credentials in `~/.netrc` (see [Credentials](#credentials))
5. `glo_90_missing`: these are tiles that are in `glo_90` but not in `glo_30`. They are over the countries Armenia and Azerbaijan. Used internally to help fill in gaps in coverage of `glo_30`.
6. `nisar_dem`: the NISAR mission DEM v1.2 [[link](https://nisar-docs.asf.alaska.edu/nisar-dem/)] - the Copernicus GLO-30 (2023_1) re-referenced to the WGS84 ellipsoid by JPL NISAR team. Only the `epsg:4326` tile set is cataloged (global coverage including ocean tiles). Since the EGM2008 geoid has already been removed from this DEM, only `dst_ellipsoidal_height=True` is supported and no geoid is applied by the stitcher. Requires Earthdata credentials in `~/.netrc` (see [Credentials](#credentials)).

 All the tiles are given in lat/lon CRS (i.e. `epsg:4326` for global tiles or `epsg:4269` for USGS tiles in North America). A notable omission to the tile sets is the Artic DEM [here](https://www.pgc.umn.edu/data/arcticdem/), which is suitable for DEMs merged at the north pole of the globe due to lat/lon distortion.

 If there are issues with obtaining dem tiles from urls embedded within the geoparquet tile tables (e.g. a `404` error as [here](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/48)), please see the [Development](#for-development) section below and/or open an issue ticket.

# DEM Transformations

Wherever possible, we do not resample the original DEMs unless specified by the user to do so. When extents are specified, we obtain the the minimum  pixel extent within the merged tile DEMs that contain that extent. Any required resampling (e.g. updating the CRS or updating the resolution because the tiles have non-square resolution at high latitudes) is done after these required translations. We importantly note that order in which these transformations are done is crucial, i.e. first translating the DEM (to either pixel- or area-center coordinates) and then resampling is different than first resampling and then translation (as affine transformations are not commutative). Here are some notes/discussions:

1. All DEMs are resampled to `epsg:4326`. Most DEMs are already in this CRS except the USGS DEMs over North America, which are in `epsg:4269`, whose `xy` projection is also `lon/lat` but has different vertical data. For our purposes, these two CRSs are almost identical. The nuanced differences between these CRS's is noted [here](https://gis.stackexchange.com/a/170854).
2. All DEM outputs will have origin and pixel spacing aligning with the original DEM tiles unless a resolution for the final product is specified, which will alter the pixel spacing.
3. Georeferenced rasters can be tied to map coordintaes using either (a) upper-left corners of pixels or (b) the pixel centers i.e. `Point` and `Area` tags in `gdal`, respectively, and seen as `{'AREA_OR_POINT: 'Point'}`. Note that tying a pixel to the upper-left cortner (i.e. `Area` tag) is the *default* pixel reference for `gdal` as indicated [here](https://gdal.org/tutorials/geotransforms_tut.html). Some helpful resources in reference to DEMs about this book-keeping are below.
   + SRTM v3, NASADEM, and TDX are [Pixel-centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904), i.e. `{'AREA_OR_POINT: 'Point'}`.
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects), i.e. `{'AREA_OR_POINT: 'Area'}`.
4. Transform geoid heights to WGS84 Ellipsoidal height. This is done using the rasters [here](https://www.agisoft.com/downloads/geoids/). We:
   + Interpolate the geoid (with cubic resampling) at the *native* DEM sample locations, i.e. before any `Area`/`Point` relabeling of the output grid, so that `dst_area_or_point` only shifts the output transform by half a pixel and never changes the height samples (see [#151](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/151))
   + Adjust the vertical datum

   Stitching `glo_30` with `dst_ellipsoidal_height=True` agrees with the independently produced [NISAR DEM](https://nisar-docs.asf.alaska.edu/nisar-dem/) (Copernicus GLO-30 with EGM2008 removed at the source by JPL) at the millimeter level; the residual is the difference between JPL's EGM2008 grid/interpolation and the 1 arcminute grid used here. See this [notebook](notebooks/analysis_and_comparison/2_Comparison_with_NISAR_DEM.ipynb).
5. All DEMs are converted to `float32` and have nodata `np.nan`. Although this can increase data size of certain rasters (SRTM is distributed in which pixels are recorded as integers), this ensures (a) easy comparison across DEMs and (b) no side-effects of the stitcher due to dtypes and/or nodata values. There is one caveat: the user can ensure that DEM nodata pixels are set to `0` using `merge_nodata_value` in `stitch_dem`, in which case `0` is filled in where `np.nan` was. We note specifying this "fill value" via `merge_nodata_value` does *not* change the nodata value of output DEM dataset (i.e. `nodata` in the rasterio profile will remain `np.nan`). When transforming to ellipsoidal heights and setting `0` as `merge_nodata_value`, the geoid values are filled in the DEMs nodata areas; if the geoid has nodata in the bounding box, this will be the source of subsequent no data.  For reference, this datatype and nodata is specified in `merge_tile_datasets` in `merge.py`. Other nodata values can be specified outside the stitcher for the application of choice (e.g. ISCE2 requires nodata to be filled as `0`).

There are some [notebooks](notebooks/analysis_and_comparison) that illustrate how tiles are merged by comparing the output of our stitcher with the original tiles.

As a performance note, when merging DEM tiles, we merge the needed tiles within the extent in memory and this process has an associated overhead. An alternative approach would be to download the tiles to disk and use virtual warping or utilize VRTs more effectively. Ultimately, the accuracy of the final DEM is our prime focus and these minor performance tradeoffs are sidelined.

# Dateline support

We assume that the supplied bounds overlap the standard lat/lon CRS grid i.e. longitudes between -/+ 180 longitude and are within -/+ 90 latitude. If there is a single dateline crossing by the supplied bounds, then the tiles are wrapped the dateline and individually translated to a particular hemisphere dicated by the bounds provided to generate a continuous raster over the area provided. We assume a maximum of one dateline crossing in the bounds you specified (if you have multiple dateline crossings, then `stitch_dem` will run out of memory). Similar wrapping tiles around the North and South poles (i.e. at -/+ 90 latitude) is *not* supported (a different CRS is what's required) and an exception will be raised.

# For Development

1. Clone this repo `git clone https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher.git`
2. Navigate with your terminal to the repo.
3. Run `pixi install` - this creates the environment and installs `dem_stitcher` in editable mode.

Linting and formatting are handled by `ruff` and exposed as pixi tasks:

```bash
pixi run lint
pixi run format
pixi run fix
```

## DEM Urls

If urls or readers need to be updated (they consistently do) or you want to add a new global or large DEM, then there are two points of contact:

1. The notebooks that format the geoparquet tile tables used for this library are [here](notebooks/organize_tile_data/)
2. The readers are [here](dem_stitcher/dem_readers.py)

The former is the more likely. When re-generating tiles, make sure to run all tests including integration tests (i.e. `pytest tests`). For example, if regenerating `glo` tiles, `glo-30` requires both resolution parameters (30 meters and 90 meters) and an additional notebook for filling in missing 30 meter tiles. These should be clearly spelled out in the notebook linked above.

# Testing

For the test suite, run `pixi run pytest tests` (or `pixi run test`, which skips the notebook tests).

There are two category of tests: unit tests and integration tests. The former can be run using `pytest tests -m 'not integration'` and similarly the latter with `pytest tests -m 'integration'`. Our unit tests are those marked without the `integration` tag (via `pytest`) that use synthetic data or data within the library to verify correct outputs of the library (e.g. that a small input raster is modified correctly). Integration tests ensure the `dem-stitcher` API works as expected, downloading the DEM tiles from their respective servers to ensure the stitcher runs to completion - the integration tests only make very basic checks to ensure the format of the ouptut data is correct (e.g. checking the output raster has a particular shape or that nodata is `np.nan`). Our integration tests also include tests that run the notebooks that serve as documentation via `papermill` (such tests have an additional tag `notebook`). Integration tests will require the `~/.netrc` setup above and working internet. Our testing workflow via Github actions currently runs the entire test suite except those tagged with `notebook`, as these tests take considerably longer to run.

# Contributing

We welcome contributions to this open-source package. To do so:

1. Create an GitHub issue ticket desrcribing what changes you need (e.g. issue-1)
2. Fork this repo
3. Make your modifications in your own fork
4. Make a pull-request (PR) in this repo with the code in your fork and tag the repo owner or a relevant contributor.

We use `ruff` to ensure some basic code quality (configured in `pyproject.toml`). These will be checked for each commit in a PR. Try to write tests wherever possible.

# Support

1. Create an GitHub issue ticket desrcribing what changes you would like to see or to report a bug.
2. We will work on solving this issue (hopefully with you).

# Acknowledgements

This tool was developed to support cloud SAR processing using ISCE2 and various research projects at JPL. The early work of this repository was done by Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard. Since the utilization of this package for GUNW generation (see this [repo](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp)), a subset of the ACCESS team, including Joseph (Joe) H. Kennedy, Simran Sangha, Grace Bato, Andrew Johnston, and Charlie Marshak, have improved this repository greatly. In particular, Joe Kennedy has lead the inclusion/development of actions, tests, packaging, distribution (including PyPI and `conda-forge`) and all the things to make this package more reliable, accessible, readable, etc. Simran Sangha has helped make sure output rasters are compatible with ISCE2 and other important bug-fixes.
