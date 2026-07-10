"""
Rebuild the pta.ipynb feature panel using only numpy/pandas (no geopandas/sklearn
available in this build sandbox). Mirrors cells 4/5/9/11/13 of pta.ipynb, but skips
the geopandas spatial join (state is not a model feature, so it isn't needed for
training -- only lat/lon bins are used).
"""
import glob
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

PTA = Path('/sessions/gallant-festive-albattani/mnt/PTA')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_build')
OUT.mkdir(parents=True, exist_ok=True)

GRID_SIZE_DEGREES = 1.0

# ---------------------------------------------------------------------------
# 1. MODIS satellite fire detections
# ---------------------------------------------------------------------------
fire_files = sorted(glob.glob(str(PTA / 'wildfire data' / '*.txt'))) + sorted(glob.glob(str(PTA / '*.txt')))
fire_files = sorted(set(fire_files))
print(f'Found {len(fire_files)} MODIS files')

fire_raw = pd.concat(
    (pd.read_csv(p).assign(source_file=Path(p).name) for p in fire_files),
    ignore_index=True,
)
fire_raw['acq_date'] = pd.to_datetime(fire_raw['acq_date'])
fire_raw['confidence'] = pd.to_numeric(fire_raw['confidence'], errors='coerce')
fire_raw = fire_raw.dropna(subset=['latitude', 'longitude', 'acq_date'])
# sanity bounding box for the US + territories
fire_raw = fire_raw[(fire_raw['latitude'].between(15, 72)) & (fire_raw['longitude'].between(-180, -60))]

fire_raw['lat_bin'] = np.floor(fire_raw['latitude'] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES
fire_raw['lon_bin'] = np.floor(fire_raw['longitude'] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES
fire_raw['grid_id'] = fire_raw['lat_bin'].round(2).astype(str) + '_' + fire_raw['lon_bin'].round(2).astype(str)

print(f'Loaded {len(fire_raw):,} satellite fire detections, '
      f'{fire_raw["acq_date"].min().date()} to {fire_raw["acq_date"].max().date()}')

daily_fire = (
    fire_raw
    .groupby(['acq_date', 'lat_bin', 'lon_bin', 'grid_id'], as_index=False)
    .agg(
        fire_count=('frp', 'size'),
        total_frp=('frp', 'sum'),
        max_frp=('frp', 'max'),
        mean_frp=('frp', 'mean'),
        mean_brightness=('brightness', 'mean'),
        max_brightness=('brightness', 'max'),
        mean_confidence=('confidence', 'mean'),
        high_confidence_count=('confidence', lambda s: (s >= 80).sum()),
        daytime_count=('daynight', lambda s: (s == 'D').sum()),
        nighttime_count=('daynight', lambda s: (s == 'N').sum()),
    )
    .rename(columns={'acq_date': 'date'})
)

# ---------------------------------------------------------------------------
# 2. Reported 2026 fire cases (with cause + state attributes)
# ---------------------------------------------------------------------------
case_raw = pd.read_csv(PTA / 'data' / '2026_fire.csv', encoding='utf-8-sig', low_memory=False)
case_raw['case_date'] = pd.to_datetime(case_raw['attr_FireDiscoveryDateTime'], errors='coerce').dt.normalize()
case_raw['latitude'] = pd.to_numeric(case_raw['attr_InitialLatitude'], errors='coerce')
case_raw['longitude'] = pd.to_numeric(case_raw['attr_InitialLongitude'], errors='coerce')
case_raw['case_acres'] = np.nan
for acres_col in ['attr_IncidentSize', 'attr_CalculatedAcres', 'attr_FinalAcres', 'poly_GISAcres']:
    if acres_col in case_raw:
        case_raw['case_acres'] = case_raw['case_acres'].fillna(pd.to_numeric(case_raw[acres_col], errors='coerce'))
case_raw['case_acres'] = case_raw['case_acres'].fillna(0)
case_raw['state_code'] = case_raw['attr_POOState'].astype(str).str.replace('US-', '', regex=False)
case_raw['fire_cause_general'] = case_raw['attr_FireCauseGeneral'].fillna('Unknown')
case_raw['fire_cause_specific'] = case_raw['attr_FireCauseSpecific'].fillna('Unknown')

case_raw = case_raw.dropna(subset=['case_date', 'latitude', 'longitude']).copy()
case_raw = case_raw[(case_raw['latitude'].between(15, 72)) & (case_raw['longitude'].between(-180, -60))]
case_raw['lat_bin'] = np.floor(case_raw['latitude'] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES
case_raw['lon_bin'] = np.floor(case_raw['longitude'] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES
case_raw['grid_id'] = case_raw['lat_bin'].round(2).astype(str) + '_' + case_raw['lon_bin'].round(2).astype(str)

print(f'Loaded {len(case_raw):,} reported fire cases, '
      f'{case_raw["case_date"].min().date()} to {case_raw["case_date"].max().date()}')

daily_cases = (
    case_raw
    .groupby(['case_date', 'lat_bin', 'lon_bin', 'grid_id'], as_index=False)
    .agg(
        case_count=('OBJECTID', 'size'),
        total_case_acres=('case_acres', 'sum'),
        max_case_acres=('case_acres', 'max'),
        mean_case_acres=('case_acres', 'mean'),
        contained_case_count=('attr_ContainmentDateTime', lambda s: s.notna().sum()),
    )
    .rename(columns={'case_date': 'date'})
)

# ---------------------------------------------------------------------------
# 3. Dense date x grid panel
# ---------------------------------------------------------------------------
dates = pd.date_range(
    min(fire_raw['acq_date'].min(), case_raw['case_date'].min()),
    max(fire_raw['acq_date'].max(), case_raw['case_date'].max()),
    freq='D',
)
grid = (
    pd.concat([
        daily_fire[['lat_bin', 'lon_bin', 'grid_id']],
        daily_cases[['lat_bin', 'lon_bin', 'grid_id']],
    ], ignore_index=True)
    .drop_duplicates('grid_id')
    .sort_values(['lat_bin', 'lon_bin'])
    .reset_index(drop=True)
)
print(f'{len(grid):,} unique 1-degree grid cells with any fire signal in 2026')

panel = (
    pd.MultiIndex.from_product([dates, grid['grid_id']], names=['date', 'grid_id'])
    .to_frame(index=False)
    .merge(grid, on='grid_id', how='left')
    .merge(daily_fire, on=['date', 'lat_bin', 'lon_bin', 'grid_id'], how='left')
    .merge(daily_cases, on=['date', 'lat_bin', 'lon_bin', 'grid_id'], how='left')
)

fire_feature_cols = [
    'fire_count', 'total_frp', 'max_frp', 'mean_frp', 'mean_brightness',
    'max_brightness', 'mean_confidence', 'high_confidence_count',
    'daytime_count', 'nighttime_count',
]
panel[fire_feature_cols] = panel[fire_feature_cols].fillna(0)
case_feature_cols = [
    'case_count', 'total_case_acres', 'max_case_acres', 'mean_case_acres',
    'contained_case_count',
]
panel[case_feature_cols] = panel[case_feature_cols].fillna(0)
panel['has_satellite_fire_today'] = (panel['fire_count'] > 0).astype(int)
panel['has_reported_case_today'] = (panel['case_count'] > 0).astype(int)

panel = panel.sort_values(['grid_id', 'date']).reset_index(drop=True)
grouped = panel.groupby('grid_id', group_keys=False)
for window in [1, 3, 7, 14]:
    shifted_satellite_count = grouped['fire_count'].shift(1)
    shifted_frp = grouped['total_frp'].shift(1)
    shifted_case_count = grouped['case_count'].shift(1)
    shifted_case_acres = grouped['total_case_acres'].shift(1)
    panel[f'satellite_fire_count_lag_{window}d'] = shifted_satellite_count.groupby(panel['grid_id']).rolling(window, min_periods=1).sum().reset_index(level=0, drop=True)
    panel[f'total_frp_lag_{window}d'] = shifted_frp.groupby(panel['grid_id']).rolling(window, min_periods=1).sum().reset_index(level=0, drop=True)
    panel[f'case_count_lag_{window}d'] = shifted_case_count.groupby(panel['grid_id']).rolling(window, min_periods=1).sum().reset_index(level=0, drop=True)
    panel[f'total_case_acres_lag_{window}d'] = shifted_case_acres.groupby(panel['grid_id']).rolling(window, min_periods=1).sum().reset_index(level=0, drop=True)


def days_since_previous_fire(series):
    days = []
    last_fire_idx = None
    for idx, has_fire in enumerate(series.to_numpy()):
        days.append(999 if last_fire_idx is None else idx - last_fire_idx)
        if has_fire == 1:
            last_fire_idx = idx
    return pd.Series(days, index=series.index)


def fire_level_from_acres(acres):
    if acres <= 0:
        return 'None'
    if acres < 10:
        return 'Low'
    if acres < 100:
        return 'Moderate'
    if acres < 1000:
        return 'High'
    return 'Extreme'


panel['days_since_satellite_fire'] = grouped['has_satellite_fire_today'].transform(days_since_previous_fire).clip(upper=999)
panel['days_since_reported_case'] = grouped['has_reported_case_today'].transform(days_since_previous_fire).clip(upper=999)
panel['reported_fire_level_today'] = panel['max_case_acres'].apply(fire_level_from_acres)
panel['dayofyear'] = panel['date'].dt.dayofyear
panel['month'] = panel['date'].dt.month
panel['sin_doy'] = np.sin(2 * np.pi * panel['dayofyear'] / 366)
panel['cos_doy'] = np.cos(2 * np.pi * panel['dayofyear'] / 366)

panel['target_case_count_next_day'] = grouped['case_count'].shift(-1)
panel['target_case_acres_next_day'] = grouped['max_case_acres'].shift(-1)
panel['target_fire_next_day'] = np.where(
    panel['target_case_count_next_day'].notna(),
    (panel['target_case_count_next_day'] > 0).astype(int),
    np.nan,
)
panel['target_fire_level_next_day'] = panel['target_case_acres_next_day'].apply(
    lambda acres: fire_level_from_acres(acres) if pd.notna(acres) else np.nan
)

print('Panel shape:', panel.shape)

# ---------------------------------------------------------------------------
# 4. Weather
# ---------------------------------------------------------------------------
weather_raw = pd.read_csv(PTA / 'data' / 'us_weather_2026_grid.csv')
weather_raw['date'] = pd.to_datetime(weather_raw['date'])
weather_raw['lat_bin'] = np.floor(pd.to_numeric(weather_raw['latitude'], errors='coerce') / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES
weather_raw['lon_bin'] = np.floor(pd.to_numeric(weather_raw['longitude'], errors='coerce') / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES

weather_value_cols = [
    'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
    'wind_speed_10m_max', 'sunshine_duration',
]
available_weather_cols = [c for c in weather_value_cols if c in weather_raw.columns]
weather_raw[available_weather_cols] = weather_raw[available_weather_cols].apply(pd.to_numeric, errors='coerce')

weather_daily = (
    weather_raw
    .dropna(subset=['date', 'lat_bin', 'lon_bin'])
    .groupby(['date', 'lat_bin', 'lon_bin'], as_index=False)[available_weather_cols]
    .mean()
)
if {'temperature_2m_max', 'temperature_2m_min'}.issubset(weather_daily.columns):
    weather_daily['temperature_2m_mean'] = (weather_daily['temperature_2m_max'] + weather_daily['temperature_2m_min']) / 2
    weather_daily['temperature_2m_range'] = weather_daily['temperature_2m_max'] - weather_daily['temperature_2m_min']
if 'sunshine_duration' in weather_daily.columns:
    weather_daily['sunshine_hours'] = weather_daily['sunshine_duration'] / 3600

weather_feature_cols = [
    c for c in [
        'temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
        'temperature_2m_range', 'precipitation_sum', 'wind_speed_10m_max',
        'sunshine_duration', 'sunshine_hours',
    ] if c in weather_daily.columns
]

panel_with_weather = panel.merge(
    weather_daily[['date', 'lat_bin', 'lon_bin'] + weather_feature_cols],
    on=['date', 'lat_bin', 'lon_bin'], how='left',
)
print('Weather date range:', weather_daily['date'].min().date(), 'to', weather_daily['date'].max().date())
print('Weather features:', weather_feature_cols)

# ---------------------------------------------------------------------------
# 5. Save
# ---------------------------------------------------------------------------
with open(OUT / 'panel_with_weather.pkl', 'wb') as f:
    pickle.dump({
        'panel': panel_with_weather,
        'weather_feature_cols': weather_feature_cols,
        'weather_daily': weather_daily,
    }, f)

# also save the raw per-incident case data (with cause + coordinates) for the
# "past date" real-history lookups and cause statistics
case_raw[[
    'case_date', 'latitude', 'longitude', 'lat_bin', 'lon_bin', 'grid_id',
    'attr_IncidentName', 'case_acres', 'state_code',
    'fire_cause_general', 'fire_cause_specific', 'attr_POOCounty',
]].to_pickle(OUT / 'case_raw.pkl')

fire_raw[['acq_date', 'latitude', 'longitude', 'lat_bin', 'lon_bin', 'grid_id', 'frp', 'confidence']].to_pickle(
    OUT / 'fire_raw.pkl'
)

print('DONE prepare_data.py')
print('max fire date:', fire_raw['acq_date'].max())
print('max case date:', case_raw['case_date'].max())
print('max weather date:', weather_daily['date'].max())
