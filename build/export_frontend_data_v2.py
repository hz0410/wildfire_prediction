"""
Export v2 frontend data: dense CONUS 0.25 grid, real 2026 FIRMS-derived
daily activity, weighted-case-control-trained MiniForest risk model,
and historical reported-cause context re-used from the v1 site (mapped
onto the new finer grid by nearest 1-degree parent cell).
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

BUILD = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/build')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2')
DATA = OUT / 'data'
DATA.mkdir(exist_ok=True, parents=True)

V1_DATA = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/website_templete/wildfire_prediction/data')
FIRMS_2026 = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/new_data/firms/modis_fires_2026.csv')

with open(BUILD / 'model_df_v2.pkl', 'rb') as f:
    d = pickle.load(f)
grid = d['grid']
weather_cols = d['weather_cols']

with open(BUILD / 'model_v2.pkl', 'rb') as f:
    m = pickle.load(f)
model = m['model']
feature_cols = m['feature_cols']
col_medians = m['col_medians']
holdout_auc = m['holdout_auc']

model_df = d['model_df']
weighted_prevalence = float(np.average(model_df['target'], weights=model_df['sampling_weight']))
print('weighted prevalence (true prior estimate):', weighted_prevalence)

print('grid cells:', len(grid))

# ---------------------------------------------------------------------------
# 1. Serialize the risk forest
# ---------------------------------------------------------------------------
def serialize_node(node):
    if node.feature is None:
        return {'p': [round(float(x), 5) for x in node.proba]}
    return {
        'f': int(node.feature),
        't': round(float(node.threshold), 5),
        'l': serialize_node(node.left),
        'r': serialize_node(node.right),
    }


def serialize_forest(mdl):
    return {
        'classes': [str(c) for c in mdl.classes_],
        'trees': [serialize_node(t) for t in mdl.trees_],
    }


forest_json = serialize_forest(model)
with open(DATA / 'forest_risk.json', 'w') as f:
    json.dump(forest_json, f)
print('risk forest trees:', len(forest_json['trees']), 'classes:', forest_json['classes'])

# ---------------------------------------------------------------------------
# 2. Rebuild a full (unsampled) daily activity table straight from raw FIRMS,
#    so cell_state / daily_events reflect real observed activity, not the
#    case-control-sampled training rows.
# ---------------------------------------------------------------------------
fires = pd.read_csv(FIRMS_2026, parse_dates=['acq_date'], low_memory=False)
fires = fires[fires['confidence'] >= 30]
if fires['type'].notna().any():
    fires = fires[fires['type'].fillna(0).eq(0)]
fires = fires[fires['latitude'].between(24, 50) & fires['longitude'].between(-125, -66)]

GRID_DEG = 0.25
fires['lat_bin'] = np.floor(fires['latitude'] / GRID_DEG) * GRID_DEG
fires['lon_bin'] = np.floor(fires['longitude'] / GRID_DEG) * GRID_DEG
fires['grid_id'] = fires['lat_bin'].round(2).astype(str) + '_' + fires['lon_bin'].round(2).astype(str)
fires = fires[fires['grid_id'].isin(set(grid['grid_id']))]

daily = fires.groupby(['grid_id', 'acq_date']).agg(
    fire_count=('latitude', 'size'),
    total_frp=('frp', 'sum'),
    max_frp=('frp', 'max'),
).reset_index().rename(columns={'acq_date': 'date'})
print('daily activity rows:', len(daily), 'active cells:', daily['grid_id'].nunique())

CUTOFF = daily['date'].max()
print('cutoff date:', CUTOFF.date())

full_dates = pd.date_range(daily['date'].min(), CUTOFF, freq='D')

# weather: reuse the same 1-degree proxy used in training, so cell_state anomaly
# and future estimates are self-consistent with what the model was trained on.
weather_path_candidates = [
    Path('/sessions/gallant-festive-albattani/mnt/PTA/data/us_weather_2026_grid.csv'),
    Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/data/us_weather_2026_grid.csv'),
]
weather_path = next((p for p in weather_path_candidates if p.exists()), None)
weather = pd.read_csv(weather_path, parse_dates=['date']) if weather_path else None
if weather is not None:
    weather['lat_bin1'] = np.floor(weather['latitude']) if 'latitude' in weather.columns else np.floor(weather['lat'])
    weather['lon_bin1'] = np.floor(weather['longitude']) if 'longitude' in weather.columns else np.floor(weather['lon'])
    weather_agg = weather.groupby(['lat_bin1', 'lon_bin1', 'date'])[weather_cols].mean().reset_index()
print('weather rows:', 0 if weather is None else len(weather_agg))

# ---------------------------------------------------------------------------
# 3. Climatology (day-of-year sinusoid fit) for each weather variable
# ---------------------------------------------------------------------------
climatology = {}
if weather is not None:
    doy = weather_agg['date'].dt.dayofyear.to_numpy()
    design = np.column_stack([
        np.ones_like(doy, dtype=float),
        np.cos(2 * np.pi * doy / 366),
        np.sin(2 * np.pi * doy / 366),
    ])
    for col in weather_cols:
        vals = weather_agg[col].to_numpy(dtype=float)
        mask = np.isfinite(vals)
        if mask.sum() < 10:
            continue
        coef, *_ = np.linalg.lstsq(design[mask], vals[mask], rcond=None)
        climatology[col] = {'a': float(coef[0]), 'b': float(coef[1]), 'c': float(coef[2])}
with open(DATA / 'climatology.json', 'w') as f:
    json.dump(climatology, f, indent=1)
print('climatology fit for', list(climatology.keys()))

# ---------------------------------------------------------------------------
# 4. Per-cell state as of cutoff (last 14 raw daily values + counters + anomaly)
# ---------------------------------------------------------------------------
grid_lookup = grid[[
    'grid_id', 'lat_bin', 'lon_bin', 'population_per_sq_km',
    'primary_road_km_per_100_sq_km', 'log_population_density',
    'distance_to_fire_station_km',
]].drop_duplicates('grid_id').copy()
_static_fill_cols = [
    'population_per_sq_km', 'primary_road_km_per_100_sq_km',
    'log_population_density', 'distance_to_fire_station_km',
]
for _c in _static_fill_cols:
    grid_lookup[_c] = grid_lookup[_c].fillna(grid_lookup[_c].median())
daily_indexed = daily.set_index(['grid_id', 'date'])

cell_state = {}
for _, cell in grid_lookup.iterrows():
    gid = cell['grid_id']
    lat_bin1 = np.floor(cell['lat_bin'])
    lon_bin1 = np.floor(cell['lon_bin'])
    last14_dates = full_dates[-14:]
    fire_count_14, total_frp_14 = [], []
    for dt in last14_dates:
        row = daily_indexed.index.get_loc((gid, dt)) if (gid, dt) in daily_indexed.index else None
        if row is not None:
            r = daily_indexed.loc[(gid, dt)]
            fire_count_14.append(float(r['fire_count']))
            total_frp_14.append(float(r['total_frp']))
        else:
            fire_count_14.append(0.0)
            total_frp_14.append(0.0)

    # days since last satellite fire, as of cutoff
    cell_dates = daily[daily['grid_id'] == gid]['date']
    if len(cell_dates):
        days_since = float((CUTOFF - cell_dates.max()).days)
    else:
        days_since = 999.0

    anom = {}
    if weather is not None:
        wcell = weather_agg[(weather_agg['lat_bin1'] == lat_bin1) & (weather_agg['lon_bin1'] == lon_bin1)]
        wcell = wcell[wcell['date'] >= (CUTOFF - pd.Timedelta(days=13))]
        for col, co in climatology.items():
            if col not in wcell.columns or len(wcell) == 0:
                anom[col] = 0.0
                continue
            doy_c = wcell['date'].dt.dayofyear.to_numpy()
            pred = co['a'] + co['b'] * np.cos(2 * np.pi * doy_c / 366) + co['c'] * np.sin(2 * np.pi * doy_c / 366)
            resid = wcell[col].to_numpy(dtype=float) - pred
            resid = resid[np.isfinite(resid)]
            anom[col] = float(resid.mean()) if len(resid) else 0.0

    cell_state[gid] = {
        'lat_bin': float(cell['lat_bin']),
        'lon_bin': float(cell['lon_bin']),
        'fire_count_14': fire_count_14,
        'total_frp_14': total_frp_14,
        'days_since_satellite_fire_cutoff': days_since,
        'weather_anomaly': anom,
    }

with open(DATA / 'cell_state.json', 'w') as f:
    json.dump(cell_state, f)
print('cell_state cells:', len(cell_state))

# ---------------------------------------------------------------------------
# 5. Sparse daily events for PAST dates (real satellite ground truth)
# ---------------------------------------------------------------------------
events_out = {}
for _, row in daily.iterrows():
    gid = row['grid_id']
    date_str = row['date'].strftime('%Y-%m-%d')
    events_out.setdefault(gid, {})[date_str] = {
        'fire_count': float(row['fire_count']),
        'total_frp': round(float(row['total_frp']), 1),
        'max_frp': round(float(row['max_frp']), 1),
    }
with open(DATA / 'daily_events.json', 'w') as f:
    json.dump(events_out, f)
print('daily_events cells with any activity:', len(events_out))

# ---------------------------------------------------------------------------
# 6. Historical reported-cause context, reused from the v1 (1-degree) site
#    since the v2 satellite-only target has no cause labels of its own.
#    Mapped onto the new finer grid via nearest 1-degree parent cell.
# ---------------------------------------------------------------------------
with open(V1_DATA / 'cell_causes.json') as f:
    v1_causes = json.load(f)


def parse_v1_key(k):
    lat_s, lon_s = k.split('_')
    return float(lat_s), float(lon_s)


v1_keys = [(k, *parse_v1_key(k)) for k in v1_causes]

cell_causes = {}
for _, cell in grid_lookup.iterrows():
    parent_lat = np.floor(cell['lat_bin'])
    parent_lon = np.floor(cell['lon_bin'])
    best_key, best_dist = None, 1e9
    for k, klat, klon in v1_keys:
        dist = abs(klat - parent_lat) + abs(klon - parent_lon)
        if dist < best_dist:
            best_dist = dist
            best_key = k
    if best_key is not None and best_dist <= 1.5:
        cell_causes[cell['grid_id']] = v1_causes[best_key]

with open(DATA / 'cell_causes.json', 'w') as f:
    json.dump(cell_causes, f)
print('cell_causes mapped for', len(cell_causes), 'of', len(grid_lookup), 'cells')

# ---------------------------------------------------------------------------
# 7. Grid index + feature meta
# ---------------------------------------------------------------------------
grid_index = grid_lookup.to_dict(orient='records')
with open(DATA / 'grid_index.json', 'w') as f:
    json.dump(grid_index, f)
print('grid_index:', len(grid_index))

with open(DATA / 'feature_meta.json', 'w') as f:
    json.dump({
        'feature_cols': feature_cols,
        'col_medians': [float(x) for x in col_medians],
        'weather_cols': weather_cols,
        'cutoff_date': CUTOFF.strftime('%Y-%m-%d'),
        'grid_resolution_deg': GRID_DEG,
        'n_grid_cells': len(grid_lookup),
        'risk_feature_importance': {
            feature_cols[i]: round(float(model.feature_importances_[i]), 5)
            for i in range(len(feature_cols))
        },
        'holdout_auc': holdout_auc,
        'weighted_prevalence': weighted_prevalence,
        'balanced_train_prior': 0.5,
    }, f, indent=1)

print('DONE export_frontend_data_v2.py')
