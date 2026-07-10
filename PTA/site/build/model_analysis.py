"""
Model analysis for the frontend:
 1. SHAP-style feature attribution for the risk model, via Shapley sampling
    values (Strumbelj & Kononenko's model-agnostic Shapley-value estimator).
    We use this instead of the `shap` package because this build sandbox has
    no scikit-learn/shap and no outbound internet for pip install -- but the
    underlying math IS Shapley-value / SHAP feature attribution, just
    computed with a from-scratch sampling estimator instead of TreeSHAP.
 2. Held-out performance metrics for both models: ROC curve, confusion
    matrix, precision/recall/F1, calibration curve, and level-model accuracy
    by class.
"""
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mini_forest import MiniForest  # noqa: F401 (needed to unpickle)

OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_build')
DATA = OUT / 'data'

with open(OUT / 'panel_with_weather.pkl', 'rb') as f:
    d = pickle.load(f)
panel_with_weather = d['panel']
weather_feature_cols = d['weather_feature_cols']

with open(OUT / 'models.pkl', 'rb') as f:
    models = pickle.load(f)
risk_model = models['risk_model']
level_model = models['level_model']
feature_cols = models['feature_cols']
col_medians = models['col_medians']

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
assert feature_cols == base_feature_cols + weather_feature_cols

model_df = (
    panel_with_weather
    .dropna(subset=['target_fire_next_day', 'target_fire_level_next_day'])
    .sort_values(['date', 'grid_id'])
    .reset_index(drop=True)
)
X = model_df[feature_cols].to_numpy(dtype=np.float64)
inds = np.where(np.isnan(X))
X[inds] = np.take(col_medians, inds[1])
y = model_df['target_fire_next_day'].to_numpy()
y_level = model_df['target_fire_level_next_day'].to_numpy()

unique_dates = np.sort(model_df['date'].unique())
cutoff_date = unique_dates[int(len(unique_dates) * 0.85)]
train_mask = (model_df['date'] < cutoff_date).to_numpy()
test_mask = ~train_mask

risk_class_idx = list(risk_model.classes_).index(1.0)
proba_test = risk_model.predict_proba(X[test_mask])[:, risk_class_idx]
y_test = y[test_mask]
level_pred_test = level_model.predict(X[test_mask])
y_level_test = y_level[test_mask]

print('test rows:', test_mask.sum(), 'positive rate:', y_test.mean())

# ---------------------------------------------------------------------------
# 1. ROC curve + confusion matrix + precision/recall/F1
# ---------------------------------------------------------------------------
def roc_curve_points(y_true, scores, n_points=60):
    qs = np.linspace(0, 1, n_points)
    thresholds = np.unique(np.quantile(scores, qs))[::-1]
    P = y_true.sum()
    N = len(y_true) - P
    fpr, tpr = [], []
    for t in thresholds:
        pred = scores >= t
        tp = ((pred == 1) & (y_true == 1)).sum()
        fp = ((pred == 1) & (y_true == 0)).sum()
        tpr.append(float(tp / P) if P > 0 else 0.0)
        fpr.append(float(fp / N) if N > 0 else 0.0)
    return fpr, tpr


def roc_auc(y_true, scores):
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    n_pos = y_true.sum()
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    sum_ranks_pos = ranks[y_true == 1].sum()
    return float((sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


fpr, tpr = roc_curve_points(y_test, proba_test)
auc = roc_auc(y_test, proba_test)

THRESH = 0.35
pred_at_thresh = (proba_test >= THRESH).astype(int)
tp = int(((pred_at_thresh == 1) & (y_test == 1)).sum())
fp = int(((pred_at_thresh == 1) & (y_test == 0)).sum())
fn = int(((pred_at_thresh == 0) & (y_test == 1)).sum())
tn = int(((pred_at_thresh == 0) & (y_test == 0)).sum())
precision = tp / (tp + fp) if (tp + fp) else 0.0
recall = tp / (tp + fn) if (tp + fn) else 0.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
accuracy = (tp + tn) / (tp + fp + fn + tn)

# calibration: bin predicted probability, compare to observed rate
n_bins = 10
bin_edges = np.linspace(0, 1, n_bins + 1)
bin_idx = np.clip(np.digitize(proba_test, bin_edges) - 1, 0, n_bins - 1)
calibration = []
for b in range(n_bins):
    mask = bin_idx == b
    if mask.sum() == 0:
        continue
    calibration.append({
        'bin_center': float((bin_edges[b] + bin_edges[b + 1]) / 2),
        'predicted_mean': float(proba_test[mask].mean()),
        'observed_rate': float(y_test[mask].mean()),
        'n': int(mask.sum()),
    })

# level model: accuracy per class
level_classes = sorted(set(y_level_test) | set(level_pred_test))
per_class = []
for c in level_classes:
    support = int((y_level_test == c).sum())
    if support == 0:
        continue
    tp_c = int(((level_pred_test == c) & (y_level_test == c)).sum())
    pred_c = int((level_pred_test == c).sum())
    precision_c = tp_c / pred_c if pred_c else 0.0
    recall_c = tp_c / support if support else 0.0
    per_class.append({
        'class': c, 'support': support,
        'precision': round(precision_c, 3), 'recall': round(recall_c, 3),
    })
level_accuracy = float((level_pred_test == y_level_test).mean())

performance = {
    'n_train_rows': int(train_mask.sum()),
    'n_test_rows': int(test_mask.sum()),
    'test_positive_rate': float(y_test.mean()),
    'roc_auc': auc,
    'roc_curve': {'fpr': fpr, 'tpr': tpr},
    'threshold': THRESH,
    'confusion_matrix': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
    'precision': round(precision, 4),
    'recall': round(recall, 4),
    'f1': round(f1, 4),
    'accuracy': round(accuracy, 4),
    'calibration': calibration,
    'level_model': {
        'accuracy': round(level_accuracy, 4),
        'per_class': per_class,
    },
    'n_trees': len(risk_model.trees_),
    'max_depth': risk_model.max_depth,
    'n_features': len(feature_cols),
}
with open(DATA / 'model_performance.json', 'w') as f:
    json.dump(performance, f, indent=1)
print('Wrote model_performance.json: AUC=%.3f  precision=%.3f  recall=%.3f  f1=%.3f  level_acc=%.3f' % (
    auc, precision, recall, f1, level_accuracy))

# ---------------------------------------------------------------------------
# 2. SHAP-style feature attribution (Shapley sampling values)
# ---------------------------------------------------------------------------
rng = np.random.default_rng(0)

# background: random sample from training data (marginal distribution)
bg_n = 150
bg_idx = rng.choice(np.where(train_mask)[0], size=bg_n, replace=False)
X_background = X[bg_idx]

# instances to explain: oversample positive class (rare) + a random sample,
# all from the held-out test period so this doubles as an out-of-sample read
test_idx_all = np.where(test_mask)[0]
pos_idx = test_idx_all[y[test_idx_all] == 1]
neg_idx = test_idx_all[y[test_idx_all] == 0]
n_pos_take = min(len(pos_idx), 120)
n_neg_take = min(len(neg_idx), 180)
inst_idx = np.concatenate([
    rng.choice(pos_idx, size=n_pos_take, replace=False) if n_pos_take else np.array([], dtype=int),
    rng.choice(neg_idx, size=n_neg_take, replace=False),
])
X_instances = X[inst_idx]
print('SHAP: explaining', len(X_instances), 'instances (%d positive) against %d background rows' % (n_pos_take, bg_n))


def shapley_sampling_values(predict_fn, X_instances, X_background, n_permutations=25, random_state=1):
    rng = np.random.default_rng(random_state)
    n_inst, n_feat = X_instances.shape
    shap_vals = np.zeros((n_inst, n_feat))
    bg_n = X_background.shape[0]
    for m in range(n_permutations):
        perm = rng.permutation(n_feat)
        bg_pick = X_background[rng.integers(0, bg_n, size=n_inst)]
        coalition = bg_pick.copy()
        prev = predict_fn(coalition)
        for feat in perm:
            coalition[:, feat] = X_instances[:, feat]
            cur = predict_fn(coalition)
            shap_vals[:, feat] += (cur - prev)
            prev = cur
    return shap_vals / n_permutations


def predict_fn(Xb):
    return risk_model.predict_proba(Xb)[:, risk_class_idx]


t0 = time.time()
shap_values = shapley_sampling_values(predict_fn, X_instances, X_background, n_permutations=25, random_state=1)
print('SHAP sampling took', round(time.time() - t0, 1), 's')

mean_abs = np.abs(shap_values).mean(axis=0)
mean_signed = shap_values.mean(axis=0)
base_value = float(predict_fn(X_background).mean())

# sanity check: base_value + sum(shap) should ~= average predicted proba of instances
avg_pred = float(predict_fn(X_instances).mean())
avg_reconstructed = base_value + mean_signed.sum()
print(f'Sanity check -- avg predicted proba: {avg_pred:.4f}, base + sum(shap): {avg_reconstructed:.4f}')

order = np.argsort(mean_abs)[::-1]
shap_summary = [{
    'feature': feature_cols[i],
    'mean_abs_shap': round(float(mean_abs[i]), 5),
    'mean_signed_shap': round(float(mean_signed[i]), 5),
} for i in order]

# a small sample of raw (feature_value, shap_value) pairs per top feature,
# enough to draw a simple beeswarm-style scatter client-side
top_k = 12
raw_points = {}
for i in order[:top_k]:
    fname = feature_cols[i]
    raw_points[fname] = {
        'feature_values': [round(float(v), 3) for v in X_instances[:, i]],
        'shap_values': [round(float(v), 5) for v in shap_values[:, i]],
    }

with open(DATA / 'shap_analysis.json', 'w') as f:
    json.dump({
        'method': 'Shapley sampling values (Strumbelj & Kononenko, 25 permutations, 150-row background)',
        'base_value': round(base_value, 5),
        'n_instances_explained': len(X_instances),
        'n_background': bg_n,
        'summary': shap_summary,
        'points': raw_points,
    }, f)
print('Wrote shap_analysis.json, top feature:', shap_summary[0])
print('DONE model_analysis.py')
