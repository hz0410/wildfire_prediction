import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mini_forest import MiniForest

OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_build')

with open(OUT / 'panel_with_weather.pkl', 'rb') as f:
    d = pickle.load(f)
panel_with_weather = d['panel']
weather_feature_cols = d['weather_feature_cols']

base_feature_cols = [
    'lat_bin', 'lon_bin', 'month', 'dayofyear', 'sin_doy', 'cos_doy',
    'satellite_fire_count_lag_1d', 'total_frp_lag_1d',
    'satellite_fire_count_lag_3d', 'total_frp_lag_3d',
    'satellite_fire_count_lag_7d', 'total_frp_lag_7d',
    'satellite_fire_count_lag_14d', 'total_frp_lag_14d',
    'case_count_lag_1d', 'total_case_acres_lag_1d',
    'case_count_lag_3d', 'total_case_acres_lag_3d',
    'case_count_lag_7d', 'total_case_acres_lag_7d',
    'case_count_lag_14d', 'total_case_acres_lag_14d',
    'days_since_satellite_fire', 'days_since_reported_case',
]
feature_cols = base_feature_cols + weather_feature_cols

model_df = (
    panel_with_weather
    .dropna(subset=['target_fire_next_day', 'target_fire_level_next_day'])
    .sort_values(['date', 'grid_id'])
    .reset_index(drop=True)
)
print('model_df shape', model_df.shape)

X = model_df[feature_cols].to_numpy(dtype=np.float64)
# median impute
col_medians = np.nanmedian(X, axis=0)
inds = np.where(np.isnan(X))
X[inds] = np.take(col_medians, inds[1])

y = model_df['target_fire_next_day'].to_numpy()
y_level = model_df['target_fire_level_next_day'].to_numpy()

# time-based holdout: last 15% of unique dates for a quick validation read
unique_dates = np.sort(model_df['date'].unique())
cutoff = unique_dates[int(len(unique_dates) * 0.85)]
train_mask = (model_df['date'] < cutoff).to_numpy()
test_mask = ~train_mask
print('train rows', train_mask.sum(), 'test rows', test_mask.sum(), 'cutoff', cutoff)

t0 = time.time()
risk_model = MiniForest(n_estimators=40, max_depth=6, min_leaf=25, bootstrap_size=6000, random_state=42)
risk_model.fit(X[train_mask], y[train_mask], feature_names=feature_cols)
print('risk_model trained in', time.time() - t0, 's')

proba_test = risk_model.predict_proba(X[test_mask])[:, list(risk_model.classes_).index(1.0)]
y_test = y[test_mask]

# simple ROC AUC (rank-based, no sklearn)
def roc_auc(y_true, scores):
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    n_pos = y_true.sum()
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    sum_ranks_pos = ranks[y_true == 1].sum()
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return auc

auc = roc_auc(y_test, proba_test)
print('Holdout ROC AUC:', auc)
print('Holdout positive rate:', y_test.mean(), 'n_test:', len(y_test))

t0 = time.time()
level_model = MiniForest(n_estimators=40, max_depth=6, min_leaf=25, bootstrap_size=6000, random_state=7)
level_model.fit(X[train_mask], y_level[train_mask], feature_names=feature_cols)
print('level_model trained in', time.time() - t0, 's')

level_pred = level_model.predict(X[test_mask])
level_acc = (level_pred == y_level[test_mask]).mean()
print('Holdout level accuracy:', level_acc)

print('\nTop risk_model feature importances:')
imp_order = np.argsort(risk_model.feature_importances_)[::-1]
for i in imp_order[:15]:
    print(f'  {feature_cols[i]:35s} {risk_model.feature_importances_[i]:.4f}')

# refit on ALL labeled data for production use
t0 = time.time()
risk_model_full = MiniForest(n_estimators=60, max_depth=6, min_leaf=25, bootstrap_size=8000, random_state=42)
risk_model_full.fit(X, y, feature_names=feature_cols)
print('risk_model_full trained in', time.time() - t0, 's')

t0 = time.time()
level_model_full = MiniForest(n_estimators=60, max_depth=6, min_leaf=25, bootstrap_size=8000, random_state=7)
level_model_full.fit(X, y_level, feature_names=feature_cols)
print('level_model_full trained in', time.time() - t0, 's')

with open(OUT / 'models.pkl', 'wb') as f:
    pickle.dump({
        'risk_model': risk_model_full,
        'level_model': level_model_full,
        'feature_cols': feature_cols,
        'col_medians': col_medians,
        'holdout_auc': auc,
        'holdout_level_acc': level_acc,
    }, f)

print('DONE train_model.py')
