"""Step 07 — produce Gourley 2017 BAMS figures + extra POT diagnostics.

Figures (in data/figures/):
    fig2a_unitpeak_scatter.png       sim vs obs unit peak Q (density-colored)
    fig2b_norm_timing_vs_area.png    norm. peak time error vs basin area
    fig3a_pct_error_map.png          spatial map of peak magnitude % error
    fig3b_timing_error_map.png       spatial map of peak timing error (h)
    table2_contingency.csv           per-model PoD/FAR/CSI/HSS at action stage
    summary_per_basin.csv            per-basin summary (used in 3a/3b)
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from . import config as C


def main():
    ap = argparse.ArgumentParser(__doc__)
    args = ap.parse_args()

    paired = pd.read_parquet(C.RESULTS_DIR / "paired_peaks.parquet")
    sites  = pd.read_csv(C.SITES_MASTER_CSV, dtype={"USGS_ID": str})
    sm     = sites.set_index("USGS_ID")

    # Add area + lat/lon for plotting
    paired = paired.merge(sites[["USGS_ID","drainage_km2","lat","lon"]],
                          on="USGS_ID", how="left")
    paired["unit_obs_q"] = paired["obs_peak_q_cms"] / paired["drainage_km2"]
    paired["unit_sim_q"] = paired["sim_max_q"]      / paired["drainage_km2"]

    colors = {"CREST": "#1f77b4", "SAC": "#2ca02c", "HP": "#d62728"}
    fig2a, ax = plt.subplots(1, 3, figsize=(15, 5), sharex=True, sharey=True)
    for axi, (m, sub) in zip(ax, paired.groupby("model")):
        sub = sub.dropna(subset=["unit_obs_q","unit_sim_q"])
        sub = sub[(sub["unit_obs_q"]>0)&(sub["unit_sim_q"]>0)]
        if sub.empty: continue
        h = axi.hist2d(sub["unit_obs_q"], sub["unit_sim_q"], bins=60,
                       norm=LogNorm(), cmap="viridis", cmin=1)
        m_max = float(max(sub["unit_obs_q"].max(), sub["unit_sim_q"].max()))
        axi.plot([1e-4, m_max], [1e-4, m_max], "w--", lw=1)
        axi.set_xscale("log"); axi.set_yscale("log")
        axi.set_title(f"{m}  n={len(sub):,}")
        axi.set_xlabel("Observed unit peak Q [m³/s/km²]")
        axi.grid(alpha=.3, which="both")
    ax[0].set_ylabel("FLASH unit peak Q [m³/s/km²]")
    fig2a.suptitle("Gourley 2017 Fig 2a — sim vs obs unit peak Q (density)", fontsize=12)
    fig2a.tight_layout()
    fig2a.savefig(C.FIG_DIR / "fig2a_unitpeak_scatter.png", dpi=140); plt.close()

    fig2b, ax = plt.subplots(figsize=(9, 5))
    for m, sub in paired.groupby("model"):
        sub = sub.dropna(subset=["drainage_km2","norm_dt"])
        ax.scatter(sub["drainage_km2"], sub["norm_dt"], s=8, alpha=.5,
                   color=colors.get(m,"k"), label=m)
    ax.axhline(0, color="k", lw=.7)
    ax.set_xscale("log")
    ax.set_xlabel("Basin area [km²]"); ax.set_ylabel("Normalized peak time error  Δt / t_c")
    ax.set_title("Gourley 2017 Fig 2b — normalized peak timing error vs basin area")
    ax.legend(); ax.grid(alpha=.3, which="both")
    fig2b.tight_layout(); fig2b.savefig(C.FIG_DIR / "fig2b_norm_timing_vs_area.png", dpi=140); plt.close()

    # Per-basin summary for spatial maps
    per = (paired.groupby(["USGS_ID","model"])
           .agg(median_pct_err=("ratio", lambda r: 100*(np.nanmedian(r)-1)),
                median_dt_min=("dt_min", "median"),
                n=("ratio","size")).reset_index())
    per = per.merge(sites[["USGS_ID","lat","lon","drainage_km2"]], on="USGS_ID", how="left")
    per.to_csv(C.RESULTS_DIR / "summary_per_basin.csv", index=False)

    for varname, title, suff, vmin, vmax in [
        ("median_pct_err", "Median peak magnitude error (%)",   "fig3a", -100, 100),
        ("median_dt_min",  "Median peak timing error (min)",    "fig3b",  -240, 240)]:
        fig, ax = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
        for axi, m in zip(ax, ("CREST","SAC","HP")):
            sub = per[per["model"]==m]
            sc = axi.scatter(sub["lon"], sub["lat"], c=sub[varname],
                             cmap="RdBu_r", vmin=vmin, vmax=vmax,
                             s=14, edgecolor="k", linewidth=.2, alpha=.85)
            axi.set_title(f"{m}  n_basins={sub['USGS_ID'].nunique()}")
            axi.set_xlabel("Longitude"); axi.grid(alpha=.3)
        ax[0].set_ylabel("Latitude")
        fig.colorbar(sc, ax=ax, shrink=.7).set_label(title)
        fig.suptitle(f"Gourley 2017 — {title}", fontsize=12)
        fig.savefig(C.FIG_DIR / f"{suff}_map.png", dpi=140); plt.close()
    print("wrote Gourley figures to", C.FIG_DIR)


if __name__ == "__main__":
    main()
