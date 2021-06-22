# Sources

# 3dep

We used the s3 bucket `prd-tnm` using the appropriate prefix (see the link below).

## Tiles

We were originally using these tiles as reference, but the links have become outdated. Find it is best to use s3 bucket directly.

3dep kml: https://www.sciencebase.gov/catalog/item/imap/4f70aa71e4b058caae3f8de1

To translate to geojson:

```
ogr2ogr -nlt POLYGON -explodecollections -skipfailures -f GeoJSON 3dep.geojson 3dep.kml 'sb:childrenBoundingBox'
```



# Ned1

We used the s3 bucket `prd-tnm` using the appropriate prefix (see the link below).

## Tiles

We were originally using these tiles as reference, but the links have become outdated. Find it is best to use s3 bucket directly.

Ned1 geojson: https://cugir.library.cornell.edu/catalog/cugir-009096

# SRTM

## Tiles

Shapefile with data: https://figshare.com/articles/dataset/Vector_grid_of_SRTM_1x1_degree_tiles/1332753

## Raster

Using links from this [site](https://dwtkns.com/srtm30m/)

Namely, `f'http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/{tile_id}.SRTMGL1.hgt.zip'` e.g. [http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N43W121.SRTMGL1.hgt.zip](http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N43W121.SRTMGL1.hgt.zip).

At some ponit, we should determine the s3 bucket in which these DEM tiles are located.

# TDX 30 meter

All of the data is [here](https://registry.opendata.aws/copernicus-dem/)

Tiles are [here](https://copernicus-dem-30m.s3.amazonaws.com/grid.zip).

And the s3 bucket is open.


