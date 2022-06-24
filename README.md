# dem-stitcher

This tool aims to (a) provide a continuous raster of Digital Elevation Raster over an area of interest and (b) perform some standard transformations for processing. Such transformations include:
+ converting the vertical datum from a reference geoid to the WGS84 ellipsoidal
+ ensuring a coordinate reference system centered at either the upper-left corner (`Area` tag) or center of the pixel (`Point` tag).

We utilize the GIS formats from `rasterio`. This tool was developed to support cloud SAR processing using ISCE2 and various research. The early work of this repository was done by Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard.

The API can be summarized as

```
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


# Installation with pip

To install dem stitcher: `pip install dem-stitcher`

Currently python 3.7 - 3.9 is supported. Python 3.10 requires a pre-release of `rasterio` (see `environments/environment-310.yml`).

## With ISCE2 or gdal

If you plan to use this stitcher with ISCE2 or require `gdal` (not just `rasterio`), then the environment will be more complicated. Currently, we have an example environment for use with staging a DEM with `isce2` in `environments/environment-isce.yml` and an associated notebook [here](./notebooks/Staging_a_DEM_for_ISCE2.ipynb), which requires older versions of `gdal` and `Proj`. The most up-to-date environment is in the Dockerized TopsApp [workflow](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/environment.yml).

## For Development

1. Clone this repo `git clone https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher.git`
2. Navigate with your terminal to the repo.
3. Create a new environment and install requirements using `conda env update --file environment.yml` (or use [`mamba`](https://github.com/mamba-org/mamba) to speed the install up)
4. Install the package from cloned repo using `python -m pip install -e .`


## Credentials

The accessing of NASADEM and SRTM require earthdata login credentials to be put into the `~/.netrc` file. If these are not present, the stitcher will
fail with `BadZipFile Error` as the request is made behind the secnes with `rasterio`. Specifically,

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

We also demonstrate how the tiles used to organize the urls for the DEMs were generated for this tool were generated in this [notebook](notebooks/organize_tile_data/Format_and_Organize_Data.ipynb).

# DEMs

The [DEMs](https://github.com/ACCESS-Cloud-Based-InSAR/dem_stitcher/tree/main/dem_stitcher/data) that can currently be used with this tool are:

```
In [1]: from dem_stitcher.datasets import DATASETS; DATASETS
Out[1]: ['srtm_v3', 'nasadem', 'glo_30', '3dep', 'ned1']
```

1. `glo-30`: Copernicus GLO-30 DEM 30 meter [[link](https://registry.opendata.aws/copernicus-dem/)]
2. The USGS DEMSs:
   - `ned1`:  Ned 1 arc-second (deprecated by USGS) [[link](https://cugir.library.cornell.edu/catalog/cugir-009096)]
   - `3dep`: 3Dep 1 arc-second[[link](https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1)]
3. `srtm_v3`: SRTM v3 [[link](https://dwtkns.com/srtm30m/)]
4. `nasadem`: Nasadem [[link](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)]

# Transformations

Wherever possible, we do not resample the original DEMs unless necessary. When extents are specified, we obtain the the minimum square pixel extent within the merged tile DEMs that contain that extent and return this. Any required resampling (e.g. updating the CRS or updating the resolution because the tiles have non-square resolution at high latitudes) is done at the end of the translations. We importantly note that first translating the DEM (to either pixel or area center coordinates) and then resampling is different than first resampling and then translation (as affine transformations like this are not commutative). As indicated above, all resampling (if required) is done at the end. Here are some notes:

1. All DEMs are resampled to `epsg:4326` (most DEMs are in this CRS except some of the USGS DEMs, which are in `epsg:4269` and is very similar CRS)
2. All DEMs meant to align with the original DEM pixels unless a resolution for the final product is specified
3. Rasters can be transformed into reference system either referring to upper-left corners of pixels or their centers (i.e. `Point` and `Area` tags in `gdal`, respectively, and seen as `{'AREA_OR_POINT: 'Point'}`. Note that `Area` is the *default* pixel reference for `gdal` as indicated [here](https://gdal.org/tutorials/geotransforms_tut.html). Some helpful resources about this book-keeping are below.
   + SRTM v3 and TDX are [Pixel-centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904), i.e. `{'AREA_OR_POINT: 'Point'}`.
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects), i.e. `{'AREA_OR_POINT: 'Area'}`.
4. Transform geoid heights to WGS84 Ellipsoidal height. This is done using the rasters [here](https://www.agisoft.com/downloads/geoids/). We:
   + Adjust the geoid to pixel/area coordinates
   + resample the geoids into the DEM reference frame
   + Adjust the vertical datum.
5. All DEMs are converted to `float32` and have nodata `np.nan`. Although this can increase data size of certain rasters (SRTM is distributed as integers), this ensures (a) easy comparison across DEMs and (b) no side-effects of the stitcher due to unusual nodata values. Note, this datatype is done in `merge_tiles` in the `stitcher.py`. Other nodata values can be specified outside the stitcher as is frequently done (e.g. ISCE2 requires nodata to be filled as `0`).

There are some [notebooks](notebooks/analysis_and_comparison) that illustrate how tiles are merged by comparing the output of our stitcher with the original tiles.

Currently, as a performance note, when merging tiles, we merge the all needed tiles into memory and this creates overhead on this front. Of course, one may elect to physically download the tiles and use virtual warping. Ultimately, the accuracy of the final DEM is our prime focus.

# Testing

1. Install `pytest`
2. Run `pytest .`

 We have an integration test (marked as `integration`) which ensures all the datasets are downloaded and can be transformed (not validated for correctness at this time). Otherwise, all tests have basic tests with mock data to illustrate how the DEM stitcher is working. The non-integration tests are as github actions via `pytest tests -m "not integration"`.

# Contributing

1. Create an GitHub issue ticket desrcribing what changes you need (e.g. issue-1)
2. Fork this repo
3. Make your modifications in your own fork
4. Make a pull-request in this repo with the code in your fork and tag the repo owner / largest contributor as a reviewer

# Support

1. Create an GitHub issue ticket desrcribing what changes you would like to see or to report a bug
2. We will work on solving this issue (hopefully with you)
