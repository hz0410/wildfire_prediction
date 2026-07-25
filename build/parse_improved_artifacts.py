import csv
import json
from pathlib import Path

SRC = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/improved_artifacts')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/data')
OUT.mkdir(parents=True, exist_ok=True)


def read_csv_rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def to_float(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            try:
                d[k] = float(d[k])
            except ValueError:
                pass
    return d


model_card = json.loads((SRC / 'improved_model_card.json').read_text())

metrics_rows = read_csv_rows(SRC / 'improved_model_metrics.csv')
numeric_metric_keys = [k for k in metrics_rows[0] if k not in ('split',)]
metrics_rows = [to_float(r, numeric_metric_keys) for r in metrics_rows]
for r in metrics_rows:
    r['rows'] = int(r['rows'])
    r['positives'] = int(r['positives'])

perm_importance = read_csv_rows(SRC / 'improved_feature_importance.csv')
perm_importance = [to_float(r, ['importance_mean', 'importance_std']) for r in perm_importance]

shap_importance = read_csv_rows(SRC / 'shap_global_importance.csv')
shap_importance = [to_float(r, ['mean_absolute_shap']) for r in shap_importance]

ablation = read_csv_rows(SRC / 'coordinate_ablation.csv')
ablation = [to_float(r, ['PR_AUC', 'ROC_AUC', 'Brier']) for r in ablation]

candidate_results = read_csv_rows(SRC / 'candidate_model_results.csv')
candidate_results = [to_float(r, ['PR_AUC', 'ROC_AUC', 'Brier']) for r in candidate_results]

bootstrap_rows = read_csv_rows(SRC / 'temporal_bootstrap_confidence_intervals.csv')
bootstrap_ci = {}
for r in bootstrap_rows:
    metric = r[''] if '' in r else r.get('Unnamed: 0')
    bootstrap_ci[metric] = {
        'lower_95': float(r['lower_95']),
        'median': float(r['median']),
        'upper_95': float(r['upper_95']),
    }

payload = {
    'model_card': model_card,
    'metrics_by_split': metrics_rows,
    'permutation_importance': perm_importance,
    'shap_importance': shap_importance,
    'coordinate_ablation': ablation,
    'candidate_results': candidate_results,
    'bootstrap_ci': bootstrap_ci,
}
(OUT / 'improved_model_analysis.json').write_text(json.dumps(payload, indent=1))
print('Wrote improved_model_analysis.json')
print('Top permutation feature:', perm_importance[0])
print('Top SHAP feature:', shap_importance[0])
print('Metrics splits:', [r['split'] for r in metrics_rows])
