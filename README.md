# dem-stitcher

![Tests](https://github.com/ACCESS-Cloud-Based-InSAR/dem_stitcher/actions/workflows/pytest.yaml/badge.svg)

This tool aims to (a) provide a continuous raster of Digital Elevation Raster over an area of interest and (b) perform common transformations for processing. Such common transformations include converting the vertical datum from a reference geoid to the WGS84 ellipsoidal *or* ensuring a pixel- or area-center coordinate reference system. We utilize the GIS formats from `rasterio`. This tool was developed to support cloud SAR processing using ISCE2 and various research. The early work of this repository was done by Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard.

The API can be summarized as

```
bounds = [-119.085, 33.402, -118.984, 35.435]
X, p = stitch_dem(bounds,
                  dem_name='glo_30',
                  dst_ellipsoidal_height=False,
                  dst_area_or_point='Area')
# X is an m x n numpy array
# p is a dictionary (or a rasterio profile) including relevant GIS metadata
```
To save the DEM, would then be:
```
with rasterio.open('dem.tif', 'w', **p) as ds:
   ds.write(X, 1)
```


# Installation with pip

Install dem stitcher: `pip install dem-stitcher`

## For Development

Clone this repo.

1. `pip install -r requirements.txt` (this will contain jupyter, pytest, flake8, etc.)
2. Install the package using `pip install -e .`


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

1. All DEMs are resampled to `epsg:4326` (most DEMs are in this CRS)
2. All DEMs are resampled to match the bounds specified and align with the original DEM pixels
3. Rasters can be transformed into pixel- or area-centered referenced raster (i.e. `Point` and `Area` tags in `gdal` as `{'AREA_OR_POINT: 'Point'}`. Note that Some helpful resources about this book-keeping are some of the DEM references:
   + SRTM v3 and TDX are [pixel centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904).
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects).
4. Transform geoid heights to WGS84 Ellipsoidal height. This is done using the rasters [here](https://www.agisoft.com/downloads/geoids/). We generally resample the geoids and into the DEM reference frame before adjusting the vertical datum.

# Testing

1. Install `pytest`.
2. Run pytest.

There are automatic github actions that run the said tests as well. Many more tests are still needed.

# Contributing

1. Create an GitHub issue ticket desrcribing what changes you need (e.g. issue-1)
2. Fork this repo
3. Make your modifications in your own fork
4. Make a pull-request in this repo with the code in your fork and tag the repo owner / largest contributor as a reviewer

## Support

Create an issue ticket.