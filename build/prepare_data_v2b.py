"""
Case-control sampled training panel for the v2 site-demo model, mirroring
advanced_pta.ipynb's sections 2-3 (new-ignition labeling + case-control
sampling with restoring weights) but scoped to 2026-only FIRMS data and the
CONUS 0.25-degree grid built in prepare_data_v2.py, since that's what's
readable in this sandbox.
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ADV = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta')
BUILD = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/build')

GRID_DEG = 0.25
CONFIDENCE_MIN = 30
PERSISTENCE_GAP_DAYS = 3
NEGATIVES_PER_POSITIVE_DAY = 5
MIN_NEGATIVES_PER_DAY = 40
RANDOM_STATE = 42

with open(BUILD / 'grid_v2.pkl', 'rb') as f:
    grid = pickle.load(f)
grid_lookup = grid.set_index('grid_id')
grid_ids = grid['grid_id'].to_numpy()

# ---------------------------------------------------------------------------
# 1. FIRMS 2026 detections -> daily fire aggregation -> new-ignition labels
# ---------------------------------------------------------------------------
usecols = ['latitude', 'longitude', 'acq_date', 'confidence', 'frp', 'brightness', 'type']
fires = pd.read_csv(ADV / 'new_data' / 'firms' / 'modis_fires_2026.csv',
                     usecols=lambda c: c in usecols, low_memory=False)
fires['date'] = pd.to_datetime(fires['acq_date'], errors='coerce').dt.normalize()
for col in ['latitude', 'longitude', 'confidence', 'frp', 'brightness', 'type']:
    fires[col] = pd.to_numeric(fires[col], errors='coerce')
fires = fires[
    fires['latitude'].between(24, 50)
    & fires['longitude'].between(-125, -66)
    & (fires['confidence'].fillna(0) >= CONFIDENCE_MIN)
].copy()
if fires['type'].notna().any():
    fires = fires[fires['type'].fillna(0).eq(0)]

fires['lat_bin'] = np.floor(fires['latitude'] / GRID_DEG) * GRID_DEG
fires['lon_bin'] = np.floor(fires['longitude'] / GRID_DEG) * GRID_DEG
fires['grid_id'] = fires['lat_bin'].round(2).astype(str) + '_' + fires['lon_bin'].round(2).astype(str)
fires = fires[fires['grid_id'].isin(set(grid_ids))].copy()
print(f'{len(fires):,} filtered 2026 detections inside the CONUS grid')

daily_fire = (
    fires.groupby(['date', 'grid_id'], as_index=False)
    .agg(fire_count=('frp', 'size'), total_frp=('frp', 'sum'), max_frp=('frp', 'max'))
    .sort_values(['grid_id', 'date'])
)
daily_fire['gap_days'] = daily_fire.groupby('grid_id')['date'].diff().dt.days
daily_fire['target_new_ignition'] = (
    daily_fire['gap_days'].isna() | (daily_fire['gap_days'] > PERSISTENCE_GAP_DAYS)
).astype('int8')
print(f"{len(daily_fire):,} active cell-days, "
      f"{daily_fire['target_new_ignition'].sum():,} new-ignition candidates")

# ---------------------------------------------------------------------------
# 2. Case-control sampling from the FULL dense grid (restores background rate)
# ---------------------------------------------------------------------------
rng = np.random.default_rng(RANDOM_STATE)
active_by_date = daily_fire.groupby('date')['grid_id'].agg(set).to_dict()
positives = daily_fire[daily_fire['target_new_ignition'].eq(1)].copy()
positives['target_date'] = positives['date']
positives['date'] = positives['target_date'] - pd.Timedelta(days=1)
positive_by_date = {date: frame for date, frame in positives.groupby('date')}

decision_dates = pd.date_range(
    fires['date'].min(), fires['date'].max() - pd.Timedelta(days=1), freq='D'
)
sampled = []
for date_value in decision_dates:
    target_date = date_value + pd.Timedelta(days=1)
    pos_day = positive_by_date.get(date_value)
    if pos_day is None:
        pos = pd.DataFrame(columns=['date', 'grid_id', 'target_date', 'total_frp', 'max_frp'])
    else:
        pos = pos_day[['date', 'grid_id', 'target_date', 'total_frp', 'max_frp']].copy()
    pos['target'] = 1
    pos['sampling_weight'] = 1.0
    if len(pos):
        sampled.append(pos)

    active = active_by_date.get(target_date, set())
    available = np.asarray([gid for gid in grid_ids if gid not in active])
    n_negative = min(len(available), max(MIN_NEGATIVES_PER_DAY, NEGATIVES_PER_POSITIVE_DAY * len(pos)))
    selected = rng.choice(available, size=n_negative, replace=False)
    neg = pd.DataFrame({'date': date_value, 'grid_id': selected})
    neg['target_date'] = target_date
    neg['total_frp'] = 0.0
    neg['max_frp'] = 0.0
    neg['target'] = 0
    neg['sampling_weight'] = len(available) / n_negative
    sampled.append(neg)

model_df = pd.concat(sampled, ignore_index=True)
model_df = model_df.join(
    grid_lookup[['lat', 'lon', 'population_per_sq_km', 'primary_road_km_per_100_sq_km',
                 'log_population_density', 'distance_to_fire_station_km']],
    on='grid_id',
)
model_df['month'] = model_df['date'].dt.month
model_df['dayofyear'] = model_df['date'].dt.dayofyear
model_df['sin_doy'] = np.sin(2 * np.pi * model_df['dayofyear'] / 366)
model_df['cos_doy'] = np.cos(2 * np.pi * model_df['dayofyear'] / 366)
print(f"{len(model_df):,} sampled rows; observed positive rate={model_df['target'].mean():.4%}")
print(f"weighted prevalence={np.average(model_df['target'], weights=model_df['sampling_weight']):.5%}")

# ---------------------------------------------------------------------------
# 3. Trailing fire-history lag features
# ---------------------------------------------------------------------------
history_source = daily_fire[['date', 'grid_id', 'fire_count', 'total_frp']].copy()
for window in [1, 3, 7, 14]:
    count_total = np.zeros(len(model_df), dtype='float32')
    frp_total = np.zeros(len(model_df), dtype='float32')
    for lag in range(window):
        shifted = history_source.copy()
        shifted['date'] = shifted['date'] + pd.Timedelta(days=lag)
        shifted = shifted.rename(columns={'fire_count': f'_count_{lag}', 'total_frp': f'_frp_{lag}'})
        model_df = model_df.merge(shifted, on=['date', 'grid_id'], how='left')
        count_total += model_df.pop(f'_count_{lag}').fillna(0).to_numpy(dtype='float32')
        frp_total += model_df.pop(f'_frp_{lag}').fillna(0).to_numpy(dtype='float32')
    model_df[f'fire_count_lag_{window}d'] = count_total
    model_df[f'frp_lag_{window}d'] = frp_total

grouped = model_df.sort_values(['grid_id', 'date']).groupby('grid_id')


def days_since_previous(has_fire):
    days, last = [], None
    for i, v in enumerate(has_fire.to_numpy()):
        days.append(999 if last is None else i - last)
        if v == 1:
            last = i
    return pd.Series(days, index=has_fire.index)


model_df = model_df.sort_values(['grid_id', 'date']).reset_index(drop=True)
model_df['has_fire_today'] = (model_df['fire_count_lag_1d'] > 0).astype(int)  # proxy, refined below
# proper same-day activity flag from daily_fire directly
active_flag = daily_fire.set_index(['date', 'grid_id'])['fire_count']
model_df['days_since_satellite_fire'] = (
    model_df.groupby('grid_id', group_keys=False)['fire_count_lag_1d']
    .apply(lambda s: (s > 0).astype(int))
    .groupby(model_df['grid_id'])
    .transform(days_since_previous)
    .clip(upper=999)
)

# ---------------------------------------------------------------------------
# 4. 2026 weather proxy (1-degree, nearest match -- see README for caveat)
# ---------------------------------------------------------------------------
weather_raw = pd.read_csv(ADV.parent / 'PTA' / 'data' / 'us_weather_2026_grid.csv') \
    if (ADV.parent / 'PTA' / 'data' / 'us_weather_2026_grid.csv').exists() \
    else pd.read_csv(ADV / 'data' / 'us_weather_2026_grid.csv')
weather_raw['date'] = pd.to_datetime(weather_raw['date'])
weather_raw['lat_bin1'] = np.floor(pd.to_numeric(weather_raw['latitude'], errors='coerce'))
weather_raw['lon_bin1'] = np.floor(pd.to_numeric(weather_raw['longitude'], errors='coerce'))
weather_cols = ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
                'wind_speed_10m_max', 'sunshine_duration']
weather_cols = [c for c in weather_cols if c in weather_raw.columns]
weather_raw[weather_cols] = weather_raw[weather_cols].apply(pd.to_numeric, errors='coerce')
weather_daily = weather_raw.groupby(['date', 'lat_bin1', 'lon_bin1'], as_index=False)[weather_cols].mean()

model_df['lat_bin1'] = np.floor(model_df['lat'])
model_df['lon_bin1'] = np.floor(model_df['lon'])
model_df = model_df.merge(weather_daily, on=['date', 'lat_bin1', 'lon_bin1'], how='left')

with open(BUILD / 'model_df_v2.pkl', 'wb') as f:
    pickle.dump({'model_df': model_df, 'weather_cols': weather_cols, 'grid': grid}, f)
print('Saved model_df_v2.pkl, shape', model_df.shape)
print('Weather coverage:', model_df[weather_cols].notna().any(axis=1).mean() if weather_cols else 0)
