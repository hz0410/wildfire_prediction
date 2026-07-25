"""
Build the v2 site-demo feature table: CONUS 0.25-degree grid, human-activity
features (population/roads/fire-station distance), 2026 FIRMS fire history,
and the 2026 weather proxy -- all things readable in this sandbox without
scikit-learn/xarray/pyarrow. This mirrors the *shape* of the real
improved_model.ipynb pipeline (same grid size, same "new ignition after 3 quiet
days" target, same human-activity fields) but is an independent
re-implementation limited to 2026 data with a coarser weather proxy, since the
real GridMET NetCDF files can't be read here. The site's Model Analysis section
shows the REAL model's real results (from improved_artifacts); this surrogate
only powers the live demo map.
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ADV = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/build')
OUT.mkdir(parents=True, exist_ok=True)

GRID_DEG = 0.25
CONFIDENCE_MIN = 30

# ---------------------------------------------------------------------------
# 1. CONUS 0.25-degree grid with human-activity features
# ---------------------------------------------------------------------------
human = pd.read_csv(ADV / 'data' / 'human_activity' / 'grid_human_activity_features.csv')
parts = human['grid_id'].str.rsplit('_', n=2, expand=True)
human['state'] = parts[0]
human['parent_lat'] = pd.to_numeric(parts[1], errors='coerce')
human['parent_lon'] = pd.to_numeric(parts[2], errors='coerce')
human = human[
    ~human['state'].isin(['AK', 'HI', 'AS', 'GU', 'MP', 'PR', 'VI'])
    & human['parent_lat'].between(24, 50)
    & human['parent_lon'].between(-125, -66)
].copy()

static_cols = [
    'grid_area_sq_km', 'county_population', 'population_per_sq_km',
    'primary_road_km', 'primary_road_km_per_100_sq_km', 'log_population_density',
]
human[static_cols] = human[static_cols].apply(pd.to_numeric, errors='coerce')
human = human.groupby(['parent_lat', 'parent_lon'], as_index=False)[static_cols].mean()

offsets = np.round(np.arange(0.125, 1.0, GRID_DEG), 3)
subcells = []
for lat_offset in offsets:
    for lon_offset in offsets:
        block = human.copy()
        block['lat'] = block['parent_lat'] + lat_offset
        block['lon'] = block['parent_lon'] + lon_offset
        subcells.append(block)
grid = pd.concat(subcells, ignore_index=True)
grid['lat_bin'] = np.floor(grid['lat'] / GRID_DEG) * GRID_DEG
grid['lon_bin'] = np.floor(grid['lon'] / GRID_DEG) * GRID_DEG
grid['grid_id'] = grid['lat_bin'].round(2).astype(str) + '_' + grid['lon_bin'].round(2).astype(str)
grid = grid.drop_duplicates('grid_id').reset_index(drop=True)
print(f'{len(grid):,} dense CONUS 0.25-degree grid cells')

# Fire-station distance: pure-numpy nearest neighbor via a coarse spatial hash
# (no scipy/sklearn BallTree available here).
stations = json.loads((ADV / 'data' / 'human_activity' / 'usgs_fire_ems_stations.geojson').read_text())
station_lat, station_lon = [], []
for feature in stations.get('features', []):
    geometry = feature.get('geometry') or {}
    xy = geometry.get('coordinates')
    if geometry.get('type') == 'Point' and xy and len(xy) >= 2:
        station_lon.append(float(xy[0]))
        station_lat.append(float(xy[1]))
station_lat = np.asarray(station_lat)
station_lon = np.asarray(station_lon)
print(f'{len(station_lat):,} fire/EMS stations')

BUCKET_DEG = 1.0
station_bucket_lat = np.floor(station_lat / BUCKET_DEG).astype(int)
station_bucket_lon = np.floor(station_lon / BUCKET_DEG).astype(int)
buckets = {}
for i in range(len(station_lat)):
    buckets.setdefault((station_bucket_lat[i], station_bucket_lon[i]), []).append(i)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


distances = np.full(len(grid), np.nan)
grid_lat = grid['lat'].to_numpy()
grid_lon = grid['lon'].to_numpy()
for idx in range(len(grid)):
    blat = int(np.floor(grid_lat[idx] / BUCKET_DEG))
    blon = int(np.floor(grid_lon[idx] / BUCKET_DEG))
    candidates = []
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            candidates.extend(buckets.get((blat + dlat, blon + dlon), []))
    if not candidates:
        continue
    cand = np.asarray(candidates)
    d = haversine_km(grid_lat[idx], grid_lon[idx], station_lat[cand], station_lon[cand])
    distances[idx] = d.min()
# fall back to a coarse global estimate for any cell with no nearby bucket match
if np.isnan(distances).any():
    fallback = np.nanmedian(distances)
    distances[np.isnan(distances)] = fallback
grid['distance_to_fire_station_km'] = distances
print('Fire-station distance computed for all grid cells (median %.1f km)' % np.nanmedian(distances))

with open(OUT / 'grid_v2.pkl', 'wb') as f:
    pickle.dump(grid, f)
print('Saved grid_v2.pkl')
