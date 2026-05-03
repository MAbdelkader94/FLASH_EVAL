"""Step 01 — build the consolidated sites_master.csv from all source files.

Inputs (placed in `data/sites/raw/`):
    Final2a_V06.txt
    Final2b_V06.txt
    0_PaperStationsList_V3.csv
    drainage_area_map_NOAA.csv
    All_USGS_HSRH_radar.csv

Output:
    data/sites/sites_master.csv

By default the master is filtered to `drainage_km2 <= 1200` (flash-flood scope).
Use --max-drainage-km2 0 to disable, or --keep-no-area to retain sites with no
drainage attribute.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .flash_grid import grid_index

RAW = C.SITES_DIR / "raw"


def _nz(x):
    s = str(x).strip().split('.')[0]
    return s.zfill(8) if s.isdigit() else s


_GAUGE_RE = re.compile(
    r"^\[Gauge\s+(?P<id>\S+)\]\s+lon=(?P<lon>\S+)\s+lat=(?P<lat>\S+)\s+basinarea=(?P<area>\S+)"
)


def load_ef5(path: Path) -> pd.DataFrame:
    rows = []
    for ln in open(path):
        m = _GAUGE_RE.match(ln.strip())
        if m:
            rows.append(dict(USGS_ID=_nz(m['id']),
                             lon_ef5=float(m['lon']),
                             lat_ef5=float(m['lat']),
                             area_ef5_km2=float(m['area'])))
    return pd.DataFrame(rows).drop_duplicates('USGS_ID')


def kirpich_h(area_km2):
    """Fallback time of concentration (Kirpich 1940 + Hack 1957 length-area)."""
    try:
        a = float(area_km2)
    except Exception:
        return np.nan
    if not np.isfinite(a) or a <= 0:
        return np.nan
    L_km = 1.4 * a ** 0.6
    S = 0.005
    L_m = L_km * 1000
    return 0.0195 * (L_m ** 0.77) * (S ** -0.385) / 60


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--out", default=str(C.SITES_MASTER_CSV))
    ap.add_argument("--max-drainage-km2", type=float, default=1200.0,
                    help="Drop sites with drainage area > this (km^2). "
                         "Flash-flood basins are usually <1000 km^2; default 1200 "
                         "leaves headroom. Set to 0 to disable the filter.")
    ap.add_argument("--keep-no-area", action="store_true",
                    help="Keep sites with no drainage area in the output "
                         "(default: drop them - tc cannot be computed).")
    args = ap.parse_args()

    f_2a   = RAW / "Final2a_V06.txt"
    f_2b   = RAW / "Final2b_V06.txt"
    f_v3   = RAW / "0_PaperStationsList_V3.csv"
    f_noaa = RAW / "drainage_area_map_NOAA.csv"
    f_rd   = RAW / "All_USGS_HSRH_radar.csv"

    if not f_2a.exists():
        raise SystemExit(f"missing {f_2a} - copy raw input files into {RAW}")

    ef5  = load_ef5(f_2a);  ef5['in_Final2a']  = True
    ef5b = load_ef5(f_2b);  ef5b['in_Final2b'] = True
    ef5_all = ef5.merge(ef5b[['USGS_ID', 'in_Final2b']], on='USGS_ID', how='outer')
    for c in ('in_Final2a', 'in_Final2b'):
        ef5_all[c] = ef5_all[c].fillna(False).astype(bool)

    v3 = pd.read_csv(f_v3, dtype={'USGS': str})
    v3['USGS_ID'] = v3['USGS'].apply(_nz)
    v3 = v3.drop_duplicates('USGS_ID')
    for c in ('area_usgs_web_page_km2', 'actionStag', 'Basin Perc',
              'Concentration_time', 'longitude', 'latitude'):
        v3[c] = pd.to_numeric(v3[c], errors='coerce')
    v3 = v3[['USGS_ID', 'timezone', 'area_usgs_web_page_km2', 'actionStag',
             'NWS_8_CH_1', 'Basin Perc', 'Concentration_time',
             'longitude', 'latitude']]
    v3.columns = ['USGS_ID', 'tz', 'area_paperlist_km2', 'action_stage_ft',
                  'nws_lid', 'radar_coverage_pct', 'tc_paperlist_mockus_h',
                  'lon_paperlist', 'lat_paperlist']
    v3['in_PaperList_V3'] = True

    noaa = pd.read_csv(f_noaa)
    noaa.columns = [c.strip() for c in noaa.columns]
    noaa['USGS_ID'] = noaa['USGS'].apply(_nz)
    noaa = noaa.drop_duplicates('USGS_ID')
    noaa['Area_km2'] = pd.to_numeric(noaa['Area_km2'], errors='coerce')

    def _find(cols, *needles):
        for c in cols:
            if all(n.lower() in c.lower() for n in needles):
                return c
        return None

    lat_n = _find(noaa.columns, 'usgs', 'lat')
    lon_n = _find(noaa.columns, 'usgs', 'long')
    rfc_n = _find(noaa.columns, 'rfc')
    hsa_n = _find(noaa.columns, 'hsa')
    state_n = _find(noaa.columns, 'state', 'ab')
    keep = ['USGS_ID', 'Area_km2']
    for c in (lat_n, lon_n, rfc_n, hsa_n, state_n):
        if c: keep.append(c)
    noaa_k = noaa[keep].copy()
    rn = {'Area_km2': 'area_noaa_km2'}
    if lat_n: rn[lat_n] = 'lat_noaa'; noaa_k[lat_n] = pd.to_numeric(noaa_k[lat_n], errors='coerce')
    if lon_n: rn[lon_n] = 'lon_noaa'; noaa_k[lon_n] = pd.to_numeric(noaa_k[lon_n], errors='coerce')
    if rfc_n: rn[rfc_n] = 'rfc'
    if hsa_n: rn[hsa_n] = 'hsa'
    if state_n: rn[state_n] = 'state'
    noaa_k.rename(columns=rn, inplace=True)
    noaa_k['in_drainage_area_NOAA'] = True

    radar = pd.read_csv(f_rd)
    radar.columns = [c.strip() for c in radar.columns]
    radar['USGS_ID'] = radar['station'].apply(_nz)
    radar = radar.drop_duplicates('USGS_ID')
    for c in ('usgs darea', 'latitude', 'longitude', 'Basin Avg HSRH (km)',
              'Basin Percentage of HSRH lt 1km',
              'Basin Percentage of HSRH lt 2km'):
        radar[c] = pd.to_numeric(radar[c], errors='coerce')
    radar_k = radar[['USGS_ID', 'usgs darea', 'latitude', 'longitude',
                     'Basin Avg HSRH (km)',
                     'Basin Percentage of HSRH lt 1km',
                     'Basin Percentage of HSRH lt 2km']].copy()
    radar_k.columns = ['USGS_ID', 'area_radar_mi2', 'lat_radar', 'lon_radar',
                       'basin_avg_hsrh_km', 'radar_pct_lt1km', 'radar_pct_lt2km']
    radar_k['area_radar_km2'] = radar_k['area_radar_mi2'] * 2.58999
    radar_k['in_HSRH_radar'] = True

    m = ef5_all.merge(v3, on='USGS_ID', how='outer')
    m = m.merge(noaa_k, on='USGS_ID', how='outer')
    m = m.merge(radar_k.drop(columns=['area_radar_mi2']), on='USGS_ID', how='outer')

    for col in ['in_Final2a', 'in_Final2b', 'in_PaperList_V3',
                'in_drainage_area_NOAA', 'in_HSRH_radar']:
        m[col] = m[col].fillna(False).astype(bool)

    m['lat'] = m['lat_ef5'].fillna(m['lat_paperlist']).fillna(
        m.get('lat_noaa', np.nan)).fillna(m['lat_radar'])
    m['lon'] = m['lon_ef5'].fillna(m['lon_paperlist']).fillna(
        m.get('lon_noaa', np.nan)).fillna(m['lon_radar'])
    m['lat_source'] = np.select(
        [m['lat_ef5'].notna(), m['lat_paperlist'].notna(),
         m.get('lat_noaa', pd.Series(False, index=m.index)).notna(),
         m['lat_radar'].notna()],
        ['ef5', 'paperlist', 'noaa', 'radar'], default='none')

    m['drainage_km2'] = m['area_ef5_km2'].fillna(m['area_paperlist_km2']) \
        .fillna(m.get('area_noaa_km2', np.nan)).fillna(m['area_radar_km2'])
    m['drainage_source'] = np.select(
        [m['area_ef5_km2'].notna(), m['area_paperlist_km2'].notna(),
         m.get('area_noaa_km2', pd.Series(False, index=m.index)).notna(),
         m['area_radar_km2'].notna()],
        ['ef5', 'paperlist', 'noaa', 'radar'], default='none')

    gi = m.apply(lambda r: grid_index(r['lat'], r['lon'])
                 if pd.notna(r['lat']) else (np.nan,) * 4, axis=1)
    m['flash_iy'] = [g[0] for g in gi]
    m['flash_ix'] = [g[1] for g in gi]
    m['flash_lat'] = [g[2] for g in gi]
    m['flash_lon'] = [g[3] for g in gi]

    m['tc_kirpich_fallback_h'] = m['drainage_km2'].apply(kirpich_h)
    m['tc_h'] = m['tc_paperlist_mockus_h'].fillna(m['tc_kirpich_fallback_h'])
    m['tc_source'] = np.select(
        [m['tc_paperlist_mockus_h'].notna(), m['tc_kirpich_fallback_h'].notna()],
        ['paperlist_mockus', 'kirpich_fallback_Hack_S0p005'], default='none')
    m['tc_h'] = m['tc_h'].clip(C.MIN_TC_HOURS, C.MAX_TC_HOURS)
    m['tc_h'] = m['tc_h'].fillna(C.DEFAULT_TC_HOURS)

    out_cols = [
        'USGS_ID', 'lat', 'lon', 'lat_source',
        'flash_iy', 'flash_ix', 'flash_lat', 'flash_lon',
        'drainage_km2', 'drainage_source',
        'tc_h', 'tc_source',
        'tc_paperlist_mockus_h', 'tc_kirpich_fallback_h',
        'nws_lid', 'action_stage_ft',
        'rfc', 'hsa', 'state', 'tz',
        'radar_coverage_pct', 'radar_pct_lt1km', 'radar_pct_lt2km',
        'basin_avg_hsrh_km',
        'in_Final2a', 'in_Final2b', 'in_PaperList_V3',
        'in_drainage_area_NOAA', 'in_HSRH_radar',
        'area_ef5_km2', 'area_paperlist_km2', 'area_radar_km2',
    ]
    out_cols = [c for c in out_cols if c in m.columns]
    m = m[out_cols].dropna(subset=['USGS_ID']).sort_values('USGS_ID').reset_index(drop=True)

    n_total = len(m)
    if not args.keep_no_area:
        n_no_area = m['drainage_km2'].isna().sum()
        m = m[m['drainage_km2'].notna()].copy()
    else:
        n_no_area = 0
    n_dropped_large = 0
    if args.max_drainage_km2 and args.max_drainage_km2 > 0:
        n_dropped_large = (m['drainage_km2'] > args.max_drainage_km2).sum()
        m = m[m['drainage_km2'] <= args.max_drainage_km2].copy()

    m.to_csv(args.out, index=False)
    print(f'wrote {args.out}  ({len(m)} sites)')
    print(f'  starting union     : {n_total:>6}')
    if n_no_area:
        print(f'  dropped no-area    : {n_no_area:>6}  (no drainage_km2; tc undefined)')
    if n_dropped_large:
        print(f'  dropped > {args.max_drainage_km2:>5g} km^2: {n_dropped_large:>6}  (out of flash-flood scope)')
    print(f'  with lat/lon       : {m["lat"].notna().sum():>6}')
    print(f'  with drainage      : {m["drainage_km2"].notna().sum():>6}')
    print(f'  with paperlist tc  : {m["tc_paperlist_mockus_h"].notna().sum():>6}')
    print(f'  with action stage  : {m["action_stage_ft"].notna().sum():>6}')
    print(f'  in Final2a         : {m["in_Final2a"].sum():>6}')


if __name__ == '__main__':
    main()
