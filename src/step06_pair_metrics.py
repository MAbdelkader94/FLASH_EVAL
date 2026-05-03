"""Step 06 — pair USGS peaks with FLASH max-Q and compute Gourley 2017 metrics.

For each (USGS peak, model) row in the merged FLASH+USGS table, compute:
    sim/obs ratio
    delta-t (sim_max_time − peak_time) in minutes
    normalized peak time error (delta-t / tc) — Gourley Fig. 2b
    unit peak Q (m³/s/km²) — Gourley Fig. 2a

Then aggregate per model:
    Pearson and Spearman correlation of paired peak Q
    PBIAS, NSE, RSR, KGE
    POD/FAR/CSI/HSS at action discharge (where available)

Outputs:
    data/results/paired_peaks.csv         per (peak, model) row
    data/results/metrics_by_model.csv     one row per model
"""
from __future__ import annotations

import argparse, glob
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def metrics(obs, sim):
    o = np.asarray(obs, float); s = np.asarray(sim, float)
    m = np.isfinite(o) & np.isfinite(s)
    o, s = o[m], s[m]
    if len(o) < 2: return dict(n=int(len(o)))
    err = s - o
    pbias = 100 * err.sum() / o.sum() if o.sum() else np.nan
    nse = 1 - (err**2).sum() / ((o - o.mean())**2).sum()
    rmse = float(np.sqrt((err**2).mean()))
    rsr = rmse / float(np.std(o)) if o.std() else np.nan
    pr = float(np.corrcoef(o, s)[0, 1])
    from scipy.stats import spearmanr
    sr = float(spearmanr(o, s).correlation)
    alpha = s.std() / o.std() if o.std() else np.nan
    beta = s.mean() / o.mean() if o.mean() else np.nan
    kge = (1 - np.sqrt((pr - 1)**2 + (alpha - 1)**2 + (beta - 1)**2)
           if all(np.isfinite([pr, alpha, beta])) else np.nan)
    return dict(n=int(len(o)), pearson=pr, spearman=sr,
                pbias=float(pbias), nse=float(nse),
                rmse=rmse, rsr=float(rsr), kge=float(kge),
                median_ratio=float(np.median(s/o)))


def contingency(o_above, s_above):
    a = int(np.sum(o_above &  s_above))
    b = int(np.sum(~o_above & s_above))
    c = int(np.sum(o_above & ~s_above))
    d = int(np.sum(~o_above & ~s_above))
    pod = a/(a+c) if (a+c) else np.nan
    far = b/(a+b) if (a+b) else np.nan
    csi = a/(a+b+c) if (a+b+c) else np.nan
    n = a+b+c+d
    ea = (a+b)*(a+c)/n if n else np.nan
    ed = (b+d)*(c+d)/n if n else np.nan
    hss = ((a+d-ea-ed)/(n-ea-ed)) if n and (n-ea-ed) else np.nan
    return dict(hits=a, false_alarms=b, misses=c, correct_neg=d,
                pod=float(pod), far=float(far), csi=float(csi), hss=float(hss))


def stage_to_q_cfs(rating_df, stage_ft):
    if rating_df is None or rating_df.empty: return np.nan
    if not np.isfinite(stage_ft): return np.nan
    x = rating_df["INDEP"].values; y = rating_df["DEP"].values
    if stage_ft < x.min() or stage_ft > x.max(): return np.nan
    return float(np.interp(stage_ft, x, y))


def main():
    ap = argparse.ArgumentParser(__doc__)
    args = ap.parse_args()

    files = sorted(glob.glob(str(C.FLASH_DIR / "*_flash_maxQ.parquet")))
    if not files:
        print("no FLASH parquets found"); return
    paired = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    paired["peak_time"]    = pd.to_datetime(paired["peak_time"], utc=True)
    paired["sim_max_time"] = pd.to_datetime(paired["sim_max_time"], utc=True)
    paired["dt_min"]   = (paired["sim_max_time"] - paired["peak_time"]).dt.total_seconds() / 60
    paired["norm_dt"]  = (paired["dt_min"] / 60) / paired["tc_h"]
    paired["ratio"]    = paired["sim_max_q"] / paired["obs_peak_q_cms"]

    paired.to_csv(C.RESULTS_DIR / "paired_peaks.csv", index=False)
    paired.to_parquet(C.RESULTS_DIR / "paired_peaks.parquet")
    print(f"paired peaks: {len(paired):,} rows")

    # Aggregate metrics per model
    rows = []
    for m, sub in paired.groupby("model"):
        d = metrics(sub["obs_peak_q_cms"].values, sub["sim_max_q"].values)
        d["model"] = m
        d["median_dt_min"] = float(np.nanmedian(sub["dt_min"]))
        d["median_norm_dt"] = float(np.nanmedian(sub["norm_dt"]))
        rows.append(d)
    summary = pd.DataFrame(rows)
    summary.to_csv(C.RESULTS_DIR / "metrics_by_model.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
