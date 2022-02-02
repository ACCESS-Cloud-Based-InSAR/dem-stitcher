# DEM Tile Sources

The best reference is the [notebook](Format_and_Organize_Data.ipynb) in this directory. We want to illustrate how the zip files used in `dem-stitcher`'s were generated. Below are some notes.

## Copernicus Glo-30

All of the data is [here](https://registry.opendata.aws/copernicus-dem/)

Tiles are [here](https://copernicus-dem-30m.s3.amazonaws.com/grid.zip).

The s3 bucket is open.

## 3dep

We used the s3 bucket `prd-tnm` using the appropriate prefix (see the link below).

### Tiles

We were originally using these tiles as reference, but the links have become outdated as the USGS and others have updated tiles. Found it is best to use s3 bucket directly.

Original 3dep kml: https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1

To translate to geojson:

```
ogr2ogr -nlt POLYGON -explodecollections -skipfailures -f GeoJSON 3dep.geojson 3dep.kml 'sb:childrenBoundingBox'
```

## Ned1

We used the s3 bucket `prd-tnm` using the appropriate prefix (see the link below).

### Tiles

We were originally using these tiles as reference, but again the links have become outdated. Found it is best to use s3 bucket directly.

Ned1 geojson: https://cugir.library.cornell.edu/catalog/cugir-009096

## SRTM

Located at the LP DAAC.

### Tiles

Shapefile with data: https://figshare.com/articles/dataset/Vector_grid_of_SRTM_1x1_degree_tiles/1332753 and then using the raster urls as seen at this [site](https://dwtkns.com/srtm30m/). These urls are formatted as `f'http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/{tile_id}.SRTMGL1.hgt.zip'` e.g. [http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N43W121.SRTMGL1.hgt.zip](http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N43W121.SRTMGL1.hgt.zip).

At some point, we should determine the s3 bucket in which these DEM tiles are located.
