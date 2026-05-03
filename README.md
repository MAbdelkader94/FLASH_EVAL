# FLASH_EVAL — V12.3 evaluation pipeline

Evaluation of NSSL FLASH (CREST / SAC-SMA / Hydrophobic) against USGS observed peaks for the **MRMS V12.3 QPE epoch**: **2025-08-05 → 2026-04-30 (UTC)**.

The pipeline is fully reproducible: clone, create the conda env, drop the raw input files into `data/sites/raw/`, then run a single shell script.

```
git clone git@github.com:MAbdelkader94/FLASH_EVAL.git
cd FLASH_EVAL
conda env create -f environment.yml
conda activate flash-eval
bash scripts/run_all.sh
```

---

## Repository layout

```
FLASH_EVAL/
├── README.md                this file
├── environment.yml          conda env (mamba/conda will install)
├── requirements.txt         pip-only fallback
├── .gitignore               keeps bulk data out of git
├── scripts/
│   └── run_all.sh           one-shot orchestrator
├── job_submission/          (HPC SLURM scripts go here later)
├── src/                     pipeline package — every step is `python -m src.stepNN`
│   ├── config.py            paths, dates, FLASH grid constants
│   ├── flash_grid.py        grid_index helper
│   ├── step01_build_sites.py
│   ├── step02_fetch_usgs.py
│   ├── step03_extract_events.py
│   ├── step04_filter_peaks.py
│   ├── step05_fetch_flash.py
│   ├── step06_pair_metrics.py
│   └── step07_figures_gourley.py
├── data/
│   ├── sites/
│   │   ├── raw/              ← drop the 5 input files here (see below)
│   │   └── sites_master.csv  ← built by step 01
│   ├── usgs/                 raw IV per site            (gitignored)
│   ├── events/               HydroTools events per site (gitignored)
│   ├── flash/                FLASH max-Q per peak       (gitignored)
│   ├── results/              master peaks + metrics
│   └── figures/              all output plots           (gitignored)
└── logs/
```

---

## 1. Install

The recommended path (HPC and laptop) is **mamba / conda**:

```bash
conda env create -f environment.yml      # or: mamba env create -f environment.yml
conda activate flash-eval
```

If you can't use conda (e.g. only pip on the cluster):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# pygrib + eccodes are easier via conda; if you must pip-install
# you'll need eccodes installed at the OS level first.
```

## 2. Provide the raw input files

Drop these five files into `data/sites/raw/` (they're already in your `FLASH-Evaluation/` working tree):

```
data/sites/raw/
├── Final2a_V06.txt                # 988 EF5 sites with FLASH-grid lat/lon
├── Final2b_V06.txt                # 125 EF5 sub-list
├── 0_PaperStationsList_V3.csv     # 3,157 sites with action stage + Mockus tc
├── drainage_area_map_NOAA.csv     # 4,997 sites with NOAA NWS info
└── All_USGS_HSRH_radar.csv        # 8,833 sites with radar coverage stats
```

## 3. Run the full pipeline

```bash
bash scripts/run_all.sh
```

That orchestrator runs the seven steps in order:

| Step | Script | What it does |
|------|--------|--------------|
| 01 | `step01_build_sites.py`     | Union all 5 source files, **filter to drainage ≤ 1200 km² AND radar coverage ≥ 60 %**, write `data/sites/sites_master.csv` (≈ 4,568 sites). Embeds FLASH grid index (iy, ix), drainage area, **time of concentration** (Mockus from PaperList where available, Kirpich+Hack fallback otherwise), action stage, NWS LID, radar coverage. Override the area cap with `--max-drainage-km2 N` (or `0` to disable). |
| 02 | `step02_fetch_usgs.py`      | Streams USGS NWIS instantaneous discharge for `2025-08-05 → 2026-04-30` for every site, **converts every timestamp to UTC**, writes `data/usgs/<USGS>.parquet`. Fully resumable. |
| 03 | `step03_extract_events.py`  | Resamples each series to hourly (per `little_hope.ipynb`), runs `hydrotools.events.event_detection.decomposition.list_events` with `halflife=6h, window=7D, min_event=6h, start_radius=6h`, writes `data/events/<USGS>_events.parquet`. |
| 04 | `step04_filter_peaks.py`    | Aggregates all events into `master_peaks.csv` and writes the **above-median** subset (default; `--filter above_p90` available). |
| 05 | `step05_fetch_flash.py`     | For every filtered peak, streams FLASH max-Q from the public AWS bucket `noaa-mrms-pds` over the window `[peak − 2·tc, peak + 2·tc]` for **all 3 models (CREST, SAC, HP)**, sampling every `FLASH_STEP_MIN` (30 min). Keeps only the max value. |
| 06 | `step06_pair_metrics.py`    | Pairs USGS peak with FLASH max → `paired_peaks.csv`. Computes per-model Pearson, Spearman, PBIAS, NSE, RSR, KGE + median Δt + normalized Δt/tc → `metrics_by_model.csv`. |
| 07 | `step07_figures_gourley.py` | Generates the Gourley 2017 BAMS figures: Fig 2a (sim/obs density), Fig 2b (norm. timing vs area), Fig 3a (% magnitude error map), Fig 3b (timing error map). |

Each step is independent and resumable — if step 05 dies after FLASH file 437 of 1000, just rerun and it'll pick up from there.

## 4. Tweak which sites / which dates

```bash
# all 988 Final2a sites only (default is "in_Final2a or in_PaperList_V3")
python -m src.step02_fetch_usgs --sites-filter "in_Final2a"

# different study window
python -m src.step02_fetch_usgs --start 2025-08-05 --end 2026-04-30
python -m src.step05_fetch_flash --peaks-csv data/results/peaks_filtered_above_median.csv

# different peak filter
python -m src.step04_filter_peaks --filter above_p90
python -m src.step05_fetch_flash --peaks-csv data/results/peaks_filtered_above_p90.csv

# subset of sites for a quick test
python -m src.step02_fetch_usgs --limit 20 --workers 4
```

All knobs live in `src/config.py`:

```python
STUDY_START_UTC   = 2025-08-05 00:00 UTC
STUDY_END_UTC     = 2026-04-30 23:59 UTC
FLASH_STEP_MIN    = 30      # FLASH sample interval inside each peak window
FLASH_WINDOW_MULT = 2       # window = ±N * tc
PEAK_FILTER       = "above_median"
HT_HALFLIFE       = "6h"    # HydroTools detection params (matches little_hope.ipynb)
HT_WINDOW         = "7D"
HT_MINIMUM_EVENT_DUR = "6h"
HT_START_RADIUS   = "6h"
```

## 5. HPC notes (UI ARGON)

- All bulk data is gitignored — the repo stays small. Host the input files and outputs on `/work` or `/scratch`, and symlink `data/` to that path before running.
- Each step is a pure Python module (`python -m src.stepNN`). Wrap any subset in a SLURM `srun` block.
- `step02` and `step05` are network-bound (NWIS / S3) — start with `--workers 4-8`. They are the only steps that benefit from many cores; steps 03 / 06 / 07 are CPU-bound and benefit from `--workers $(nproc)`.
- An example SLURM submission script will be added under `job_submission/` once you share the cluster's preferred MPI / partition flags.

## 6. Reproducibility / units / time-zones

- All discharge values are in **m³/s** (SI). cfs values are kept only inside `data/usgs/*.parquet` for round-tripping.
- All timestamps are **UTC**. NWIS data are localised from their reported `tz_cd` then converted.
- All basin areas are in **km²**.
- Time of concentration is in **hours**.

---

## What's where after a successful run

| file | description |
|---|---|
| `data/sites/sites_master.csv`          | every site (~10k) with FLASH grid index, t_c, drainage, AHPS, radar |
| `data/usgs/<USGS>.parquet`             | raw 15-min IV in UTC |
| `data/events/<USGS>_events.parquet`    | per-site HydroTools events |
| `data/results/master_peaks.csv`        | every event from every site (peak time UTC, peak Q cms, unit Q) |
| `data/results/peaks_filtered_above_median.csv` | the subset used for FLASH pairing |
| `data/flash/<USGS>_flash_maxQ.parquet` | FLASH max-Q per peak per model |
| `data/results/paired_peaks.csv`        | row-per-(peak, model) pair, ratios, Δt, normalised Δt/tc |
| `data/results/metrics_by_model.csv`    | Pearson/Spearman/PBIAS/NSE/RSR/KGE + median Δt per model |
| `data/results/summary_per_basin.csv`   | per-(basin, model) median % error and Δt for the spatial maps |
| `data/figures/fig2a_*.png` etc.        | Gourley 2017 figures |

## References

- Gourley, J.J. et al. (2017). The FLASH project. *BAMS*, 98(2), 361-372.
- Mockus, V. (1961). NEH-4 unit hydrograph lag time formula (NRCS).
- Kirpich, Z.P. (1940). Time of concentration of small agricultural watersheds.
- Hack, J.T. (1957). Studies of longitudinal stream profiles in Virginia and Ma
## Time of concentration used in the FLASH window

Step 05 sizes the FLASH search window as `peak ± 2 · t_c`, using
`tc_kirpich_fallback_h` from `sites_master.csv` (Kirpich 1940 with
Hack 1957 length-area + 0.5 % default slope). This is uniformly
defined across all sites, unlike the PaperList Mockus value which
only exists for ~2,500 of the 4,568 filtered sites.

If you prefer the PaperList Mockus t_c where available, edit the
single line in `src/step05_fetch_flash.py` that reads `tc_kirpich_fallback_h`
and switch it to `tc_h` (the existing fallback chain).
