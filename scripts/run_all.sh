#!/usr/bin/env bash
# Full pipeline orchestrator. Run from the ARGON/ directory.
#
#     bash scripts/run_all.sh
#
# Each step is resumable; reruns skip already-done sites/peaks.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "[01] build sites_master.csv"
python -m src.step01_build_sites

echo "[02] fetch USGS instantaneous Q (UTC) for V12.3 epoch"
python -m src.step02_fetch_usgs --workers 6

echo "[03] HydroTools event detection per site"
python -m src.step03_extract_events --workers 4

echo "[04] aggregate + filter peaks (above-median by default)"
python -m src.step04_filter_peaks --filter above_median

echo "[05] stream FLASH max-Q in [peak - 2*tc, peak + 2*tc] (3 models)"
python -m src.step05_fetch_flash --workers 2

echo "[06] pair USGS peaks vs FLASH max + Gourley metrics"
python -m src.step06_pair_metrics

echo "[07] build Gourley 2017 figures"
python -m src.step07_figures_gourley

echo "DONE.  See data/results/ and data/figures/"
