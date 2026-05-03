"""Step 04 — produce a master peaks CSV and apply the per-site filter.

Reads every <USGS>_events.parquet under data/events/, joins the basin
attributes from sites_master.csv, applies the configured peak filter
(default: above per-site median), and writes:

    data/results/master_peaks.csv          all events
    data/results/peaks_filtered.csv        the subset used for FLASH pairing

All units metric. peak_time stored in UTC.
"""
from __future__ import annotations

import argparse, glob
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--sites-csv", default=str(C.SITES_MASTER_CSV))
    ap.add_argument("--filter", default=C.PEAK_FILTER,
                    choices=("above_median", "above_p90", "all"))
    args = ap.parse_args()

    sites = pd.read_csv(args.sites_csv, dtype={"USGS_ID": str})
    sm = sites.set_index("USGS_ID")
    files = sorted(glob.glob(str(C.EVENTS_DIR / "*_events.parquet")))
    print(f"loading {len(files)} per-site event files")
    rows = []
    for f in files:
        sid = Path(f).stem.split("_")[0]
        d = pd.read_parquet(f)
        if d.empty: continue
        d["USGS_ID"] = sid
        if sid in sm.index:
            for c in ("lat", "lon", "drainage_km2", "tc_h", "tc_kirpich_fallback_h", "flash_iy",
                      "flash_ix", "action_stage_ft", "nws_lid"):
                d[c] = sm.loc[sid].get(c, np.nan)
        rows.append(d)
    master = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if master.empty:
        print("no events found"); return

    cols = ["USGS_ID", "lat", "lon", "drainage_km2", "tc_h",
            "flash_iy", "flash_ix", "tc_kirpich_fallback_h",
            "start", "end", "peak_time",
            "peak_q_cms", "peak_q_unit_cms_per_km2",
            "action_stage_ft", "nws_lid"]
    master = master[[c for c in cols if c in master.columns]]
    master["peak_time"] = pd.to_datetime(master["peak_time"], utc=True)
    master.to_csv(C.RESULTS_DIR / "master_peaks.csv", index=False)
    master.to_parquet(C.RESULTS_DIR / "master_peaks.parquet")
    print(f"master_peaks: {len(master):,} events from {master.USGS_ID.nunique()} sites")

    if args.filter == "all":
        sub = master.copy()
    elif args.filter == "above_median":
        med = master.groupby("USGS_ID")["peak_q_cms"].transform("median")
        sub = master[master["peak_q_cms"] >= med]
    else:
        p90 = master.groupby("USGS_ID")["peak_q_cms"].transform(lambda s: s.quantile(.90))
        sub = master[master["peak_q_cms"] >= p90]
    sub.to_csv(C.RESULTS_DIR / f"peaks_filtered_{args.filter}.csv", index=False)
    sub.to_parquet(C.RESULTS_DIR / f"peaks_filtered_{args.filter}.parquet")
    print(f"peaks_filtered_{args.filter}: {len(sub):,} events")


if __name__ == "__main__":
    main()
