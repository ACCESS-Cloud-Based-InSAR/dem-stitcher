import netrc
from pathlib import Path


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
