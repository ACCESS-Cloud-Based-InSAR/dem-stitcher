import geopandas as gpd
import json
import gzip
import shapely
from rasterio.crs import CRS
from typing import Union
from pathlib import Path


def read_geojson_gzip(input_zip_path: Union[str, Path]) -> gpd.GeoDataFrame:
    with gzip.GzipFile(input_zip_path, 'r') as file_in:
        data_gjson = json.loads(file_in.read().decode('utf-8'))
    return gpd.GeoDataFrame.from_features(data_gjson['features'],
                                          crs=CRS.from_epsg(4326))


def to_geojson_obj(geodataframe: gpd.geodataframe.GeoDataFrame):
    features = geodataframe.to_dict('records')

    def mapping_geojson(entry):
        geometry = entry.pop('geometry')
        new_entry = {"type": "Feature",
                     "properties": entry,
                     "geometry": shapely.geometry.mapping(geometry)}
        return new_entry
    features = list(map(mapping_geojson, features))
    geojson = {"type": "FeatureCollection",
               "features": features
               }
    return geojson


def to_geojson_gzip(geodataframe: gpd.geodataframe.GeoDataFrame,
                    dest_path: str):
    geojson_ob = to_geojson_obj(geodataframe)
    with gzip.GzipFile(dest_path, 'w') as file_out:
        file_out.write(json.dumps(geojson_ob).encode('utf-8'))
    return dest_path
