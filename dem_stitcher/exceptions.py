class NoDEMCoverage(Exception):
    "Throw this exception if extent/bounds does not cover any available DEM tiles"
    pass


class DEMNotSupported(Exception):
    "Throw this exception if DEM Name is not supported"
    pass
