# dem_stitcher

![tests](https://github.com/aria-jpl/dem_stitcher/actions/workflows/pytest/badge.svg)

The purpose of this repo is to download Digital Elevation Model (DEM) tiles and do some basic transformations so that they can be ingested into ISCE2 for the ARIA pipeline. We could see this being used in different applications. Meant to be "plugged-in" to other python routines.

This is the joint work of Charlie Marshak, David Bekaert, Michael Denbina, and Marc Simard.

Please look at the demonstration [here](notebooks/Demo.ipynb).

# Installation with pip


1. Download the `requirements.txt` and install them: `pip install -r requirements.txt`
2. Install dem stitcher: `pip install dem_stitcher`

# Installation for Development

Tested with 3.8.5 Anaconda Python.

1. `pip install -r requirements.txt`
2. Install the package either:
      + `pip install .` (or to make editable `pip install -e .`)
      + `pip install ...` from github as [here](https://stackoverflow.com/a/8256424)


## Credentials

The virtual reading of Nasadem and SRTM require earthdata login credentials to be put into the `~/.netrc` file. If these are not present, the tiler will
fail with `BadZipFile Error` as the request is made behind the secnes with `rasterio`/`gdal`.

```
machine urs.earthdata.nasa.gov
    login <username>
    password <password>
```

# DEMs

The DEMs we have are:

1. The USGS DEMSs:
   - Ned 1 arc-second (deprecated) [[link](https://cugir.library.cornell.edu/catalog/cugir-009096)]
   - 3Dep 1 arc-second[[link](https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1)]
2. SRTM v3 [[link](https://dwtkns.com/srtm30m/)]
3. Nasadem [[link](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)]
4. Tandem-X 30 meter (GLO-30) [[link](https://registry.opendata.aws/copernicus-dem/)]

Look at this [readme](notebooks_tile_data/README.md) and this [notebook](notebooks_tile_data/Format_Data.ipynb) for some more information.

# Transformations

1. Merge tiles from server
2. Resample to `epsg:4326`
3. (optional; default `True`) Pixel centered referenced raster ensuring (a) half-pixel shift in the north-west direction if the original raster tiles are centered around the UL corner point and (b) tagging the data with `{'AREA_OR_POINT: 'Point'}`.
   + SRTM v3 and TDX are [pixel centered](https://github.com/OSGeo/gdal/issues/1505#issuecomment-489469904)
   + The USGS DEMs are [not](https://www.usgs.gov/core-science-systems/eros/topochange/science/srtm-ned-vertical-differencing?qt-science_center_objects=0#qt-science_center_objects)
4. (optional; default `True`) - transform vertical heights to WGS84 Ellipsoidal height.

# Testing

1. Install `papermill` and `pytest`.
2. Install a new jupyter kernel to reference `dem_stitcher` with `python -m ipykernel install --user --name dem_stitcher` (the notebooks use this kernel name).
3. Run pytest.

There are automatic github actions that run the said tests as well.

## Contributing

1. Create an GitHub issue ticket desrcribing what changes you need (e.g. issue-1)
2. Fork this repo
3. Make your modifications in your own fork
4. Make a pull-request in this repo with the code in your fork and tag the repo owner / largest contributor as a reviewer

## Support

Create an issue ticket.