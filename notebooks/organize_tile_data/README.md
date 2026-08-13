# DEM Tile Sources

The best reference is the [notebook](0_Format_and_Organize_Data.ipynb) in this directory. We want to illustrate how the geoparquet tile tables used in `dem-stitcher` were generated (stored in `src/dem_stitcher/data/*.parquet` with `zstd` compression). Below are some notes.

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

## SRTM and NASADEM

Located at the LP DAAC Earthdata Cloud archive (the old `e4ftl01.cr.usgs.gov` urls are dead; see this [forum thread](https://forum.earthdata.nasa.gov/viewtopic.php?p=25179)). Downloading requires Earthdata login credentials in `~/.netrc`.

### Tiles

Shapefile with tile extents: https://figshare.com/articles/dataset/Vector_grid_of_SRTM_1x1_degree_tiles/1332753.

The urls are formatted as:

- SRTM: `f'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/{tile_id}.SRTMGL1.hgt/{tile_id}.SRTMGL1.hgt.zip'` e.g. [N43W121](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/N43W121.SRTMGL1.hgt/N43W121.SRTMGL1.hgt.zip)
- NASADEM: `f'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_{tile_id.lower()}/NASADEM_HGT_{tile_id.lower()}.zip'` e.g. [n43w121](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n43w121/NASADEM_HGT_n43w121.zip)
