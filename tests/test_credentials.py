import pytest

from dem_stitcher.credentials import ensure_earthdata_credentials

"""From DockerizedTopsapp - author Joe Kennedy and Forrest Williams"""


def test_main_check_earthdata_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    netrc = tmp_path / ".netrc"
    netrc.write_text("machine foobar.nasa.gov login foo password bar")

    ensure_earthdata_credentials(host="foobar.nasa.gov")
    assert netrc.read_text() == "machine foobar.nasa.gov login foo password bar"

    with pytest.raises(ValueError):
        ensure_earthdata_credentials()

    netrc.write_text("machine urs.earthdata.nasa.gov login foo password bar")
    ensure_earthdata_credentials()
    assert netrc.read_text() == "machine urs.earthdata.nasa.gov login foo password bar"
