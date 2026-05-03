"""Project-wide constants. Paths are relative to the repo root."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

# ---- Paths ----
ROOT = Path(__file__).resolve().parents[1]    # ARGON/
DATA = ROOT / "data"
SITES_DIR    = DATA / "sites"
USGS_DIR     = DATA / "usgs"        # raw IV (gitignored)
EVENTS_DIR   = DATA / "events"      # per-site HydroTools events
FLASH_DIR    = DATA / "flash"       # streamed FLASH samples (per peak event)
RESULTS_DIR  = DATA / "results"     # paired tables + metrics
FIG_DIR      = DATA / "figures"
LOG_DIR      = ROOT / "logs"

for d in (USGS_DIR, EVENTS_DIR, FLASH_DIR, RESULTS_DIR, FIG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

SITES_MASTER_CSV = SITES_DIR / "sites_master.csv"

# ---- Study window (V12.3 MRMS QPE epoch) ----
STUDY_START_UTC = dt.datetime(2025, 8, 5,  0, 0, tzinfo=dt.timezone.utc)
STUDY_END_UTC   = dt.datetime(2026, 4, 30, 23, 59, tzinfo=dt.timezone.utc)
EPOCH_LABEL     = "V12.3"

# ---- USGS NWIS ----
NWIS_IV_URL    = "https://nwis.waterservices.usgs.gov/nwis/iv/"
CFS_TO_CMS     = 0.028316846592
USGS_PARAM     = "00060"           # discharge

# ---- HydroTools event detection (matches little_hope.ipynb) ----
HT_HALFLIFE             = "6h"
HT_WINDOW               = "7D"
HT_MINIMUM_EVENT_DUR    = "6h"
HT_START_RADIUS         = "6h"

# ---- Peak filter ----
PEAK_FILTER             = "above_median"   # also: "above_p90", "all"

# ---- FLASH AWS bucket ----
FLASH_AWS_BUCKET        = "noaa-mrms-pds"
FLASH_AWS_PREFIX_FMT    = "CONUS/FLASH_{model}_{product}_00.00/{yyyymmdd}/"
FLASH_AWS_FILE_FMT      = "MRMS_FLASH_{model}_{product}_00.00_{yyyymmdd}-{hhmmss}.grib2.gz"
FLASH_MODELS            = ("CREST", "SAC", "HP")
FLASH_PRODUCTS          = ("MAXSTREAMFLOW", "MAXUNITSTREAMFLOW")
FLASH_STEP_MIN          = 30                # sample interval within ±2tc window
FLASH_WINDOW_MULT       = 2                  # window = ±N * tc

# ---- FLASH grid geometry (CONUS, 0.01 deg) ----
FLASH_LAT0, FLASH_DLAT  = 54.995, -0.01
FLASH_LON0, FLASH_DLON  = -129.995, 0.01
FLASH_NY, FLASH_NX      = 3500, 7000

# ---- Reasonable defaults / safeguards ----
DEFAULT_TC_HOURS         = 3.0     # used only when neither paperlist nor Kirpich is available
MIN_TC_HOURS             = 0.5
MAX_TC_HOURS             = 24.0
USGS_FETCH_WORKERS       = 6
FLASH_FETCH_WORKERS      = 8
