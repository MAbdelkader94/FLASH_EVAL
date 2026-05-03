"""FLASH CONUS grid helper — single function `grid_index` and `s3_key`."""
from __future__ import annotations
import datetime as dt
import numpy as np
from . import config as C


def grid_index(lat: float, lon: float):
    """Return (iy, ix, snapped_lat, snapped_lon) for the FLASH CONUS grid."""
    if not (np.isfinite(lat) and np.isfinite(lon)):
        return (np.nan, np.nan, np.nan, np.nan)
    iy = int(round((lat - C.FLASH_LAT0) / C.FLASH_DLAT))
    ix = int(round((lon - C.FLASH_LON0) / C.FLASH_DLON))
    iy = max(0, min(C.FLASH_NY - 1, iy))
    ix = max(0, min(C.FLASH_NX - 1, ix))
    return iy, ix, C.FLASH_LAT0 + iy * C.FLASH_DLAT, C.FLASH_LON0 + ix * C.FLASH_DLON


def s3_key(model: str, product: str, when: dt.datetime) -> str:
    pref = C.FLASH_AWS_PREFIX_FMT.format(model=model, product=product,
                                          yyyymmdd=when.strftime("%Y%m%d"))
    fname = C.FLASH_AWS_FILE_FMT.format(model=model, product=product,
                                         yyyymmdd=when.strftime("%Y%m%d"),
                                         hhmmss=when.strftime("%H%M%S"))
    return pref + fname
