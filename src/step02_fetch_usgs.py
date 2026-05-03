"""Step 02 — fetch USGS instantaneous discharge for V12.3 epoch in UTC.

Pulls 15-min IV from NWIS for every site listed in --sites-filter
(default: in_Final2a == True or in_PaperList_V3 == True).
Each site → one parquet under data/usgs/  with the columns
    datetime  (UTC, tz-aware)
    q_cfs
    q_cms

Resumable: writes <USGS>.done marker so re-runs skip completed sites.
"""
from __future__ import annotations

import argparse, sys, time, os
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from . import config as C


def _nz(x):
    s = str(x).strip().split('.')[0]
    return s.zfill(8) if s.isdigit() else s


TZ_MAP = {"EST": "Etc/GMT+5", "EDT": "Etc/GMT+4",
          "CST": "Etc/GMT+6", "CDT": "Etc/GMT+5",
          "MST": "Etc/GMT+7", "MDT": "Etc/GMT+6",
          "PST": "Etc/GMT+8", "PDT": "Etc/GMT+7",
          "AKST": "Etc/GMT+9", "AKDT": "Etc/GMT+8",
          "HST": "Etc/GMT+10", "UTC": "UTC"}


def fetch_site_iv(site_id: str, start_utc, end_utc, sess: requests.Session
                  ) -> pd.DataFrame | None:
    """Fetch IV for [start, end] in UTC. Returns DataFrame or None."""
    params = dict(format="rdb", sites=site_id, parameterCd=C.USGS_PARAM,
                  startDT=start_utc.strftime("%Y-%m-%d"),
                  endDT=end_utc.strftime("%Y-%m-%d"),
                  siteStatus="all")
    try:
        r = sess.get(C.NWIS_IV_URL, params=params, timeout=180)
    except Exception as e:
        print(f"  http fail {site_id}: {e}"); return None
    if r.status_code != 200:
        return None
    rows = [ln for ln in r.text.splitlines() if not ln.startswith("#")]
    if len(rows) < 3:
        return None
    df = pd.read_csv(StringIO("\n".join(rows)), sep="\t", skiprows=[1])
    val_col = next((c for c in df.columns if c.endswith("_00060")), None)
    if val_col is None:
        return None
    df = df.rename(columns={val_col: "q_cfs"})
    df["q_cfs"] = pd.to_numeric(df["q_cfs"], errors="coerce")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    # Convert to UTC using tz_cd column when present
    if "tz_cd" in df.columns and not df["tz_cd"].isna().all():
        common = df["tz_cd"].mode().iloc[0]
        target = TZ_MAP.get(common, "UTC")
        df["datetime"] = (df["datetime"]
                          .dt.tz_localize(target,
                                          nonexistent="shift_forward",
                                          ambiguous="NaT")
                          .dt.tz_convert("UTC"))
    else:
        df["datetime"] = df["datetime"].dt.tz_localize("UTC", nonexistent="shift_forward",
                                                       ambiguous="NaT")

    df = df.dropna(subset=["datetime"]).drop_duplicates(subset=["datetime"])
    df = df.set_index("datetime").sort_index()
    df["q_cms"] = df["q_cfs"] * C.CFS_TO_CMS
    return df[["q_cfs", "q_cms"]]


def process_site(site_id, start, end, sess, force=False):
    out = C.USGS_DIR / f"{site_id}.parquet"
    done = C.USGS_DIR / f"{site_id}.done"
    if done.exists() and not force:
        return done.read_text()
    df = fetch_site_iv(site_id, start, end, sess)
    if df is None or df.empty:
        done.write_text("empty"); return "empty"
    df.to_parquet(out)
    done.write_text(f"ok {len(df)}")
    return f"ok {len(df)}"


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--start", default=C.STUDY_START_UTC.strftime("%Y-%m-%d"))
    ap.add_argument("--end",   default=C.STUDY_END_UTC.strftime("%Y-%m-%d"))
    ap.add_argument("--workers", type=int, default=C.USGS_FETCH_WORKERS)
    ap.add_argument("--sites-csv", default=str(C.SITES_MASTER_CSV))
    ap.add_argument("--sites-filter",
                    default="in_Final2a or in_PaperList_V3",
                    help='pandas .query() expression on sites_master.csv')
    ap.add_argument("--limit", type=int, default=0,
                    help="process only first N sites (debug)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import datetime as dt
    start = dt.datetime.fromisoformat(args.start).replace(tzinfo=dt.timezone.utc)
    end   = dt.datetime.fromisoformat(args.end  ).replace(tzinfo=dt.timezone.utc)

    sites = pd.read_csv(args.sites_csv, dtype={"USGS_ID": str})
    sub = sites.query(args.sites_filter).copy()
    if args.limit:
        sub = sub.head(args.limit)
    ids = sub["USGS_ID"].astype(str).map(_nz).tolist()
    print(f"site filter:  {args.sites_filter}")
    print(f"sites to process: {len(ids)}")
    print(f"period UTC:   {start.date()}  →  {end.date()}")

    sess = requests.Session()
    sess.headers["User-Agent"] = "FLASH-EVAL/0.1 (mohamed-abdelkader@uiowa.edu)"

    t0 = time.time()
    ok = empty = 0
    with ThreadPoolExecutor(max_workers=args.workers) as p:
        futs = {p.submit(process_site, sid, start, end, sess, args.force): sid
                for sid in ids}
        for fut in as_completed(futs):
            r = fut.result()
            if r.startswith("ok"): ok += 1
            elif r == "empty":     empty += 1
    print(f"done ok={ok} empty={empty} in {time.time()-t0:.1f}s")


if __name__ == '__main__':
    main()
