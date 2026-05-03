"""Step 05 — for each filtered USGS peak, stream FLASH max-Q in [peak − 2*tc, peak + 2*tc].

For each (USGS peak, FLASH model, FLASH product) the code:
    1. Builds a list of timestamps every FLASH_STEP_MIN minutes covering
       [peak − N*tc, peak + N*tc]   (N = FLASH_WINDOW_MULT, default 2)
    2. Streams each grib2.gz from the public NOAA AWS bucket
       `noaa-mrms-pds`, decodes the value at the gauge cell (in memory,
       no disk cache), keeps only the max value & its timestamp.
    3. Writes one row per (peak, model, product) to:
        data/flash/<USGS>_flash_maxQ.parquet

Resumable: each per-peak result is keyed by event_id; reruns skip rows
that already exist.
"""
from __future__ import annotations

import argparse, datetime as dt, gzip, io, os, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config as C
from .flash_grid import s3_key

S3_ROOT = "https://noaa-mrms-pds.s3.amazonaws.com"


def _fetch_value(url, iy, ix, sess):
    import pygrib
    try:
        r = sess.get(url, timeout=45)
    except Exception:
        return None
    if r.status_code == 404: return None
    if r.status_code != 200: return None
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as gz:
            grb = gz.read()
    except Exception:
        return None
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as t:
        t.write(grb); tmp = t.name
    try:
        gs = pygrib.open(tmp)
        msg = gs.message(1)
        v = msg.values[iy, ix]
        if np.ma.is_masked(v): return float("nan")
        return float(v)
    except Exception:
        return None
    finally:
        try: os.unlink(tmp)
        except OSError: pass


def fetch_max_for_peak(peak_time_utc, tc_h, iy, ix, model, product,
                       step_min=C.FLASH_STEP_MIN,
                       window_mult=C.FLASH_WINDOW_MULT,
                       n_workers=C.FLASH_FETCH_WORKERS,
                       sess: requests.Session | None = None):
    sess = sess or requests.Session()
    half = dt.timedelta(hours=tc_h * window_mult)
    start = (peak_time_utc - half).replace(second=0, microsecond=0)
    start = start - dt.timedelta(minutes=start.minute % step_min)
    end   = peak_time_utc + half
    sched = []
    cur = start
    while cur <= end:
        sched.append(cur); cur += dt.timedelta(minutes=step_min)
    urls = [(t, f"{S3_ROOT}/{s3_key(model, product, t)}") for t in sched]

    def fetch(item):
        t, url = item
        v = _fetch_value(url, iy, ix, sess)
        return t, v

    rows = []
    with ThreadPoolExecutor(max_workers=n_workers) as p:
        for t, v in p.map(fetch, urls):
            if v is None: continue
            rows.append((t, v))
    if not rows: return None
    df = pd.DataFrame(rows, columns=["time", "value"]).sort_values("time")
    i = int(df["value"].values.argmax())
    return dict(sim_max_q=float(df["value"].iloc[i]),
                sim_max_time=df["time"].iloc[i],
                n_files_used=len(df))


def process_site(usgs_id, sub_peaks, sites_meta, force=False):
    """Process all filtered peaks at one site, writing one parquet."""
    out = C.FLASH_DIR / f"{usgs_id}_flash_maxQ.parquet"
    sm = sites_meta.set_index("USGS_ID").loc[usgs_id]
    iy = int(sm["flash_iy"]); ix = int(sm["flash_ix"])
    tc_h = float(sm["tc_h"])

    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    sess = requests.Session()
    sess.headers["User-Agent"] = "FLASH-EVAL/0.1 (mohamed-abdelkader@uiowa.edu)"
    rows = []
    for _, p in sub_peaks.iterrows():
        peak_t = pd.Timestamp(p["peak_time"]).to_pydatetime().replace(tzinfo=dt.timezone.utc)
        for m in C.FLASH_MODELS:
            for prod in ("MAXSTREAMFLOW",):  # only MAXSTREAMFLOW by default; add MAXUNITSTREAMFLOW if you want
                key = (str(p["peak_time"]), m, prod)
                if not have.empty and ((have[["peak_time","model","product"]].astype(str)
                        == [str(p["peak_time"]), m, prod]).all(axis=1)).any() and not force:
                    continue
                r = fetch_max_for_peak(peak_t, tc_h, iy, ix, m, prod, sess=sess)
                if r is None: continue
                rows.append(dict(USGS_ID=usgs_id, peak_time=p["peak_time"],
                                 obs_peak_q_cms=p["peak_q_cms"],
                                 tc_h=tc_h, model=m, product=prod,
                                 sim_max_q=r["sim_max_q"],
                                 sim_max_time=r["sim_max_time"],
                                 n_files_used=r["n_files_used"]))
    if rows:
        new = pd.DataFrame(rows)
        full = pd.concat([have, new], ignore_index=True) if not have.empty else new
        full.drop_duplicates(subset=["peak_time","model","product"], keep="last", inplace=True)
        full.to_parquet(out)
    return out, len(rows)


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--peaks-csv",
                    default=str(C.RESULTS_DIR / f"peaks_filtered_{C.PEAK_FILTER}.csv"))
    ap.add_argument("--sites-csv", default=str(C.SITES_MASTER_CSV))
    ap.add_argument("--limit-sites", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2,
                    help="number of parallel sites; each site uses FLASH_FETCH_WORKERS for files")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    sites = pd.read_csv(args.sites_csv, dtype={"USGS_ID": str})
    peaks = pd.read_csv(args.peaks_csv, dtype={"USGS_ID": str})
    peaks["peak_time"] = pd.to_datetime(peaks["peak_time"], utc=True)
    site_ids = peaks["USGS_ID"].unique().tolist()
    if args.limit_sites: site_ids = site_ids[:args.limit_sites]
    print(f"sites with filtered peaks: {len(site_ids)}")
    print(f"total peaks to process   : {len(peaks)}")

    t0 = time.time()
    n_rows_written = 0
    with ThreadPoolExecutor(max_workers=args.workers) as p:
        futs = {p.submit(process_site, sid, peaks[peaks.USGS_ID == sid], sites, args.force): sid
                for sid in site_ids}
        for fut in as_completed(futs):
            out, n = fut.result()
            n_rows_written += n
            print(f"  {out.name}: +{n} rows")
    print(f"done {time.time()-t0:.1f}s  rows added={n_rows_written}")


if __name__ == "__main__":
    main()
