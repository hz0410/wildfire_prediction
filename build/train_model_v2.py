import pickle
import time
from pathlib import Path

import numpy as np

from mini_forest import MiniForest

BUILD = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/build')

with open(BUILD / 'model_df_v2.pkl', 'rb') as f:
    d = pickle.load(f)
model_df = d['model_df']
weather_cols = d['weather_cols']

feature_cols = [
    'lat', 'lon', 'month', 'dayofyear', 'sin_doy', 'cos_doy',
    'fire_count_lag_1d', 'frp_lag_1d', 'fire_count_lag_3d', 'frp_lag_3d',
    'fire_count_lag_7d', 'frp_lag_7d', 'fire_count_lag_14d', 'frp_lag_14d',
    'days_since_satellite_fire',
    'population_per_sq_km', 'primary_road_km_per_100_sq_km',
    'log_population_density', 'distance_to_fire_station_km',
] + weather_cols

X = model_df[feature_cols].to_numpy(dtype=np.float64)
col_medians = np.nanmedian(X, axis=0)
inds = np.where(np.isnan(X))
X[inds] = np.take(col_medians, inds[1])
y = model_df['target'].to_numpy()
w = model_df['sampling_weight'].to_numpy()

# time-based holdout: last 15% of dates
unique_dates = np.sort(model_df['date'].unique())
cutoff = unique_dates[int(len(unique_dates) * 0.85)]
train_mask = (model_df['date'] < cutoff).to_numpy()
test_mask = ~train_mask
print('train rows', train_mask.sum(), 'test rows', test_mask.sum(), 'cutoff', cutoff)

t0 = time.time()
model = MiniForest(n_estimators=60, max_depth=7, min_leaf=20, bootstrap_size=8000, random_state=42)
model.fit(X[train_mask], y[train_mask], feature_names=feature_cols, sample_weight=w[train_mask])
print('trained in', time.time() - t0, 's')

proba_test = model.predict_proba(X[test_mask])[:, list(model.classes_).index(1)]
y_test = y[test_mask]
w_test = w[test_mask]


def weighted_roc_auc(y_true, scores, weights):
    order = np.argsort(scores)
    y_o, w_o = y_true[order], weights[order]
    w_pos = w_o * (y_o == 1)
    w_neg = w_o * (y_o == 0)
    cum_neg = np.cumsum(w_neg)
    total_pos = w_pos.sum()
    total_neg = w_neg.sum()
    if total_pos == 0 or total_neg == 0:
        return float('nan')
    auc = np.sum(w_pos * cum_neg) / (total_pos * total_neg)
    return float(auc)


auc = weighted_roc_auc(y_test, proba_test, w_test)
print('Weighted holdout ROC AUC:', auc)
print('Weighted positive rate (test):', np.average(y_test, weights=w_test))

print('\nTop feature importances:')
order = np.argsort(model.feature_importances_)[::-1]
for i in order[:15]:
    print(f'  {feature_cols[i]:32s} {model.feature_importances_[i]:.4f}')

# refit on all data for production use
t0 = time.time()
model_full = MiniForest(n_estimators=80, max_depth=7, min_leaf=20, bootstrap_size=10000, random_state=42)
model_full.fit(X, y, feature_names=feature_cols, sample_weight=w)
print('full model trained in', time.time() - t0, 's')

with open(BUILD / 'model_v2.pkl', 'wb') as f:
    pickle.dump({
        'model': model_full,
        'feature_cols': feature_cols,
        'col_medians': col_medians,
        'holdout_auc': auc,
        'weather_cols': weather_cols,
    }, f)
print('DONE train_model_v2.py')
