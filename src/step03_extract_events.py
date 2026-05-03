"""Step 03 — HydroTools event detection on each per-site USGS parquet.

Resamples to hourly (per little_hope.ipynb), runs ev.list_events with
matching parameters, extracts per-event peak Q (m^3/s) and peak time (UTC).

Output: data/events/<USGS>_events.parquet
        columns: start, end, peak_time, peak_q_cms, peak_q_unit_cms_per_km2
"""
from __future__ import annotations

import argparse, glob, os, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from . import config as C


def detect_events_one(site_id: str, sites_df: pd.DataFrame, force=False) -> str:
    out = C.EVENTS_DIR / f"{site_id}_events.parquet"
    done = C.EVENTS_DIR / f"{site_id}.done"
    if done.exists() and not force:
        return done.read_text()
    src = C.USGS_DIR / f"{site_id}.parquet"
    if not src.exists():
        done.write_text("no_usgs"); return "no_usgs"
    df = pd.read_parquet(src)
    if df.empty:
        done.write_text("empty_usgs"); return "empty_usgs"
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    # Resample hourly per little_hope convention; HydroTools needs monotonic ts
    s = df["q_cms"].resample("1h").first().ffill()
    if s.notna().sum() < 200:
        done.write_text("too_short"); return "too_short"
    from hydrotools.events.event_detection import decomposition as ev
    events = ev.list_events(s, halflife=C.HT_HALFLIFE, window=C.HT_WINDOW,
                            minimum_event_duration=C.HT_MINIMUM_EVENT_DUR,
                            start_radius=C.HT_START_RADIUS)
    if events.empty:
        done.write_text("no_events"); return "no_events"
    rows = []
    sm = sites_df.set_index("USGS_ID").loc[site_id] if site_id in sites_df["USGS_ID"].values else None
    area = float(sm["drainage_km2"]) if sm is not None and pd.notna(sm["drainage_km2"]) else float("nan")
    for _, e in events.iterrows():
        seg = s.loc[e.start:e.end]
        if seg.empty: continue
        rows.append(dict(start=e.start, end=e.end,
                         peak_time=seg.idxmax(),
                         peak_q_cms=float(seg.max()),
                         peak_q_unit_cms_per_km2=float(seg.max())/area if area else float("nan")))
    out_df = pd.DataFrame(rows)
    out_df.to_parquet(out)
    done.write_text(f"ok {len(out_df)}")
    return f"ok {len(out_df)}"


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sites-csv", default=str(C.SITES_MASTER_CSV))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    sites = pd.read_csv(args.sites_csv, dtype={"USGS_ID": str})
    cands = [Path(p).stem for p in glob.glob(str(C.USGS_DIR / "*.parquet"))]
    if args.limit:
        cands = cands[:args.limit]
    print(f"sites to process: {len(cands)}")
    t0 = time.time()
    n_ok = 0
    with ProcessPoolExecutor(max_workers=args.workers) as p:
        futs = {p.submit(detect_events_one, sid, sites, args.force): sid for sid in cands}
        for fut in as_completed(futs):
            r = fut.result()
            if r.startswith("ok"): n_ok += 1
    print(f"done in {time.time()-t0:.1f}s  ok={n_ok}/{len(cands)}")


if __name__ == "__main__":
    main()
