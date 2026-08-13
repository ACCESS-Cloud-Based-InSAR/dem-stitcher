import netrc
import tempfile
from pathlib import Path

import rasterio


def ensure_earthdata_credentials(
    host: str = 'urs.earthdata.nasa.gov',
) -> None:
    """
    Ensure earthdata credentials in netrc are provided in ~/.netrc.

    Source: DockerizedTopsapp / Authors: Joseph Kennedy, Forrest Williams, and Andrew Johnston

    Earthdata username and password may be provided by, in order of preference, one of:
       * `netrc_file`
       * `username` and `password`
    and will be written to the ~/.netrc file if it doesn't already exist.
    """
    netrc_file = Path.home() / '.netrc'
    try:
        dot_netrc = netrc.netrc(netrc_file)
        _, _, _ = dot_netrc.authenticators(host)
    except (FileNotFoundError, netrc.NetrcParseError, TypeError):
        raise ValueError(f'Please provide valid Earthdata login credentials via {netrc_file}')


def earthdata_gdal_env(**kwargs: str) -> rasterio.Env:
    """Get a rasterio environment that authenticates with Earthdata login (via ~/.netrc) when reading urls.

    Earthdata cloud redirects through urs.earthdata.nasa.gov and requires a cookie jar to persist the session.

    Use as a context manager around `rasterio.open` and any reads from the opened datasets:

        with earthdata_gdal_env():
            with rasterio.open(url) as ds:
                arr = ds.read()
    """
    cookie_path = str(Path(tempfile.gettempdir()) / 'dem_stitcher_earthdata_cookies.txt')
    return rasterio.Env(
        GDAL_HTTP_NETRC='YES',
        GDAL_HTTP_COOKIEFILE=cookie_path,
        GDAL_HTTP_COOKIEJAR=cookie_path,
        **kwargs,
    )
