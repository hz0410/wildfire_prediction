"""
Export everything the static frontend needs:
 - forest_risk.json / forest_level.json : serialized MiniForest trees (so the
   trained random forest can run live, client-side, for any future 2026 date)
 - cell_state.json : per grid-cell state as of the cutoff date (last-14-day
   raw daily series so lag features can be recomputed exactly for any future
   date; days-since-fire counters; last observed weather + seasonal anomaly)
 - climatology.json : global seasonal (day-of-year) fit for each weather
   variable, used to estimate future weather when no forecast is available
 - daily_events.json : sparse per (date, grid) real observations for PAST
   dates (<= cutoff) -- ground truth, not a prediction
 - cell_causes.json : real historical FireCauseGeneral/Specific counts
   aggregated in a ~2-degree neighborhood around each grid cell
 - grid_index.json : list of all grid cells with lat/lon centers, for
   nearest-cell address matching
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_build')
DATA = OUT / 'data'
DATA.mkdir(exist_ok=True)

with open(OUT / 'panel_with_weather.pkl', 'rb') as f:
    d = pickle.load(f)
panel = d['panel']
weather_feature_cols = d['weather_feature_cols']

with open(OUT / 'models.pkl', 'rb') as f:
    models = pickle.load(f)
risk_model = models['risk_model']
level_model = models['level_model']
feature_cols = models['feature_cols']
col_medians = models['col_medians']

case_raw = pd.read_pickle(OUT / 'case_raw.pkl')

CUTOFF = panel['date'].max()  # 2026-06-26 (last date with real fire+case history)
print('cutoff date:', CUTOFF.date())


# ---------------------------------------------------------------------------
# 1. Serialize the forests
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


def serialize_forest(model):
    return {
        'classes': [str(c) for c in model.classes_],
        'trees': [serialize_node(t) for t in model.trees_],
    }


risk_forest_json = serialize_forest(risk_model)
level_forest_json = serialize_forest(level_model)
with open(DATA / 'forest_risk.json', 'w') as f:
    json.dump(risk_forest_json, f)
with open(DATA / 'forest_level.json', 'w') as f:
    json.dump(level_forest_json, f)
print('risk forest trees:', len(risk_forest_json['trees']), 'classes:', risk_forest_json['classes'])
print('level forest trees:', len(level_forest_json['trees']), 'classes:', level_forest_json['classes'])

with open(DATA / 'feature_meta.json', 'w') as f:
    json.dump({
        'feature_cols': feature_cols,
        'col_medians': [float(x) for x in col_medians],
        'weather_feature_cols': weather_feature_cols,
        'cutoff_date': CUTOFF.strftime('%Y-%m-%d'),
        'risk_feature_importance': {
            feature_cols[i]: round(float(risk_model.feature_importances_[i]), 5)
            for i in range(len(feature_cols))
        },
        'holdout_auc': models['holdout_auc'],
        'holdout_level_acc': models['holdout_level_acc'],
    }, f, indent=1)

# ---------------------------------------------------------------------------
# 2. Global seasonal climatology fit per weather variable (day-of-year sinusoid)
# ---------------------------------------------------------------------------
climatology = {}
doy = panel['dayofyear'].to_numpy()
design = np.column_stack([
    np.ones_like(doy, dtype=float),
    np.cos(2 * np.pi * doy / 366),
    np.sin(2 * np.pi * doy / 366),
])
for col in weather_feature_cols:
    vals = panel[col].to_numpy(dtype=float)
    mask = np.isfinite(vals)
    if mask.sum() < 10:
        continue
    coef, *_ = np.linalg.lstsq(design[mask], vals[mask], rcond=None)
    climatology[col] = {'a': float(coef[0]), 'b': float(coef[1]), 'c': float(coef[2])}
with open(DATA / 'climatology.json', 'w') as f:
    json.dump(climatology, f, indent=1)
print('climatology fit for', list(climatology.keys()))

# ---------------------------------------------------------------------------
# 3. Per-cell state as of cutoff (last 14 raw daily values + counters + weather anomaly)
# ---------------------------------------------------------------------------
panel_sorted = panel.sort_values(['grid_id', 'date'])
cell_state = {}
grid_ids = panel['grid_id'].unique()

# precompute climatology prediction for each row's doy so we can get residual anomaly
clim_pred = {}
for col, co in climatology.items():
    clim_pred[col] = co['a'] + co['b'] * np.cos(2 * np.pi * doy / 366) + co['c'] * np.sin(2 * np.pi * doy / 366)
for col in climatology:
    panel[f'_clim_{col}'] = clim_pred[col]
    panel[f'_anom_{col}'] = panel[col] - panel[f'_clim_{col}']

grouped = panel.groupby('grid_id')
for gid, g in grouped:
    g = g.sort_values('date')
    last = g.iloc[-1]
    last14 = g.tail(14)
    entry = {
        'lat_bin': float(last['lat_bin']),
        'lon_bin': float(last['lon_bin']),
        'fire_count_14': [float(x) for x in last14['fire_count']],
        'total_frp_14': [float(x) for x in last14['total_frp']],
        'case_count_14': [float(x) for x in last14['case_count']],
        'total_case_acres_14': [float(x) for x in last14['total_case_acres']],
        'days_since_satellite_fire_cutoff': float(last['days_since_satellite_fire']),
        'days_since_reported_case_cutoff': float(last['days_since_reported_case']),
    }
    anom = {}
    for col in climatology:
        vals = g[f'_anom_{col}'].dropna()
        anom[col] = float(vals.tail(14).mean()) if len(vals) else 0.0
    entry['weather_anomaly'] = anom
    cell_state[gid] = entry

with open(DATA / 'cell_state.json', 'w') as f:
    json.dump(cell_state, f)
print('cell_state cells:', len(cell_state))

# ---------------------------------------------------------------------------
# 4. Sparse daily events for PAST dates (real ground truth, not predictions)
# ---------------------------------------------------------------------------
events = panel[(panel['fire_count'] > 0) | (panel['case_count'] > 0)].copy()
events_out = {}
for _, row in events.iterrows():
    gid = row['grid_id']
    date_str = row['date'].strftime('%Y-%m-%d')
    events_out.setdefault(gid, {})[date_str] = {
        'fire_count': float(row['fire_count']),
        'total_frp': round(float(row['total_frp']), 1),
        'case_count': float(row['case_count']),
        'max_case_acres': round(float(row['max_case_acres']), 1),
        'reported_fire_level': row['reported_fire_level_today'],
    }
with open(DATA / 'daily_events.json', 'w') as f:
    json.dump(events_out, f)
print('daily_events cells with any activity:', len(events_out))

# ---------------------------------------------------------------------------
# 5. Cause distribution per cell (2-degree neighborhood), from real case data
# ---------------------------------------------------------------------------
cell_causes = {}
case_coords = case_raw[['lat_bin', 'lon_bin', 'fire_cause_general', 'fire_cause_specific']].copy()
grid_lookup = panel[['grid_id', 'lat_bin', 'lon_bin']].drop_duplicates('grid_id')
for _, cell in grid_lookup.iterrows():
    nearby = case_coords[
        (case_coords['lat_bin'].between(cell['lat_bin'] - 2, cell['lat_bin'] + 2)) &
        (case_coords['lon_bin'].between(cell['lon_bin'] - 2, cell['lon_bin'] + 2))
    ]
    if len(nearby) == 0:
        continue
    general_counts = nearby['fire_cause_general'].value_counts().head(4)
    specific_counts = nearby['fire_cause_specific'].value_counts().head(5)
    cell_causes[cell['grid_id']] = {
        'n_nearby_cases': int(len(nearby)),
        'general': {str(k): int(v) for k, v in general_counts.items()},
        'specific': {str(k): int(v) for k, v in specific_counts.items()},
    }
with open(DATA / 'cell_causes.json', 'w') as f:
    json.dump(cell_causes, f)
print('cell_causes computed for', len(cell_causes), 'cells')

# ---------------------------------------------------------------------------
# 6. Grid index for nearest-cell lookup
# ---------------------------------------------------------------------------
grid_index = grid_lookup.to_dict(orient='records')
with open(DATA / 'grid_index.json', 'w') as f:
    json.dump(grid_index, f)
print('grid_index:', len(grid_index))

print('DONE export_frontend_data.py')
