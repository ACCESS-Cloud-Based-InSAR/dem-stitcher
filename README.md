# Dem Stitcher

The purpose of this repo is to download Digital Elevation Model (DEM) tiles and do some basic transformations so that they can be ingested into ISCE2 for the ARIA pipeline. We could see this being used in different applications.

This is the joint work of Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard.

# Installation

Tested with 3.8.5 Anaconda Python.

1. `pip install -r requirements.txt`
2. `conda -c conda-forge install gdal` (gdal only for building the VRT)
3. Install the package either:
      + `pip install .` (or to make editable `pip install -e .`)
      + `pip install from github as [here](https://stackoverflow.com/a/8256424)

We will consolidate dependencies into `conda` at some point - I still just prefer pip as its faster.

# DEMs

The DEMs we have are:

1. The USGS DEMSs:
   - Ned 1 arc-second (deprecated) [[link](https://cugir.library.cornell.edu/catalog/cugir-009096)]
   - 3Dep 1 arc-second[[link](https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1)]
2. SRTM v3 [[link](https://dwtkns.com/srtm30m/)]
3. Tandem-X 30 meter (GLO-30) [[link](https://registry.opendata.aws/copernicus-dem/)]

Look at this [readme](notebooks_tile_data/README.md) and this [notebook](notebooks_tile_data/Format%20Data.ipynb) for some more information.

# Transformations

1. Merge tiles from server
2. Resample to `epsg:4326`
3. (optional; default `True`) Pixel centered referenced raster ensuring (a) half-pixel shift in the north-west direction if the original raster tiles are centered around the UL corner point and (b) tagging the data with `{'AREA_OR_POINT: 'Point'}`.
   + SRTM v3 and TDX are [pixel centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904)
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects)
4. (optional; default `True`) - Ellipsoidal height correction

