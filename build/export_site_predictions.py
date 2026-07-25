"""
Run this once in the SAME local environment you used for improved_model.ipynb
(the one with scikit-learn, xarray, joblib, pandas/pyarrow already installed).
It does not need Claude/Cowork at all -- just:

    cd /Users/haowenzhang/Documents/research/advanced_pta
    python export_site_predictions.py

It rebuilds the dense national 0.25-degree grid (same construction as
advanced_pta.ipynb section 1), attaches REAL recent gridMET weather and REAL
FIRMS fire-history features for the most recent RECENT_DAYS the weather files
cover, and runs your actual trained+calibrated model
(`improved_artifacts/improved_wildfire_model.joblib`) on every cell for every
one of those days -- not a re-implementation, the real thing.

Output: improved_artifacts/site_predictions.csv.gz
That folder is already shared with Claude, so you do not need to upload or
paste anything back -- just tell Claude you ran it (or it'll notice next time
it looks).

Adjust RECENT_DAYS below if you want more/less history. Bigger = bigger file
and slower to run, but lets the website show a short recent trend per address
instead of just the latest single day.
"""
from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd
import xarray as xr
from sklearn.neighbors import BallTree

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Config -- edit if you want
# ---------------------------------------------------------------------------
RECENT_DAYS = 14          # how many of the most recent covered days to score
GRID_DEG = 0.25
LAG_WINDOWS = [1, 3, 7, 14]
CONFIDENCE_MIN = 30

ROOT = Path(__file__).resolve().parent
ARTIFACT_DIR = ROOT / "improved_artifacts"
MODEL_FILE = ARTIFACT_DIR / "improved_wildfire_model.joblib"
HUMAN_FILE = ROOT / "data" / "human_activity" / "grid_human_activity_features.csv"
STATION_FILE = ROOT / "data" / "human_activity" / "usgs_fire_ems_stations.geojson"
FIRE_DIR = ROOT / "new_data" / "firms"
WEATHER_DIR = ROOT / "new_data" / "weather" / "gridmet"
OUT_FILE = ARTIFACT_DIR / "site_predictions.csv.gz"

WEATHER_VARIABLES = ["tmmx", "tmmn", "pr", "vs", "rmin", "vpd", "erc", "fm100"]

print("Project root:", ROOT)
if not MODEL_FILE.exists():
    raise FileNotFoundError(f"Missing {MODEL_FILE} -- run improved_model.ipynb through section 14 first.")

bundle = joblib.load(MODEL_FILE)
feature_cols = bundle["feature_cols"]
print("Loaded model:", bundle["model_name"], "| features:", len(feature_cols))

# ---------------------------------------------------------------------------
# 1. Rebuild the dense national 0.25-degree grid (mirrors advanced_pta.ipynb #1)
# ---------------------------------------------------------------------------
human = pd.read_csv(HUMAN_FILE)
parts = human["grid_id"].str.rsplit("_", n=2, expand=True)
human["state"] = parts[0]
human["parent_lat"] = pd.to_numeric(parts[1], errors="coerce")
human["parent_lon"] = pd.to_numeric(parts[2], errors="coerce")
human = human[
    ~human["state"].isin(["AK", "HI", "AS", "GU", "MP", "PR", "VI"])
    & human["parent_lat"].between(24, 50)
    & human["parent_lon"].between(-125, -66)
].copy()

static_cols = [
    "grid_area_sq_km", "county_population", "population_per_sq_km",
    "primary_road_km", "primary_road_km_per_100_sq_km", "log_population_density",
]
human[static_cols] = human[static_cols].apply(pd.to_numeric, errors="coerce")
human = human.groupby(["parent_lat", "parent_lon"], as_index=False)[static_cols].mean()

offsets = np.arange(0.125, 1.0, GRID_DEG)
subcells = []
for lat_offset in offsets:
    for lon_offset in offsets:
        block = human.copy()
        block["lat"] = block["parent_lat"] + lat_offset
        block["lon"] = block["parent_lon"] + lon_offset
        subcells.append(block)
grid = pd.concat(subcells, ignore_index=True)
grid["lat_bin"] = np.floor(grid["lat"] / GRID_DEG) * GRID_DEG
grid["lon_bin"] = np.floor(grid["lon"] / GRID_DEG) * GRID_DEG
grid["grid_id"] = grid["lat_bin"].round(2).astype(str) + "_" + grid["lon_bin"].round(2).astype(str)
grid = grid.drop_duplicates("grid_id").reset_index(drop=True)

if STATION_FILE.exists():
    stations_json = json.loads(STATION_FILE.read_text())
    coords = []
    for feature in stations_json.get("features", []):
        geometry = feature.get("geometry") or {}
        xy = geometry.get("coordinates")
        if geometry.get("type") == "Point" and xy and len(xy) >= 2:
            coords.append((float(xy[1]), float(xy[0])))
    if coords:
        tree = BallTree(np.radians(np.asarray(coords)), metric="haversine")
        distance, _ = tree.query(np.radians(grid[["lat", "lon"]].to_numpy()), k=1)
        grid["distance_to_fire_station_km"] = distance[:, 0] * 6371.0088
    else:
        grid["distance_to_fire_station_km"] = np.nan
else:
    grid["distance_to_fire_station_km"] = np.nan

print(f"{len(grid):,} dense 0.25-degree grid cells")

# ---------------------------------------------------------------------------
# 2. Find the most recent decision dates the weather files actually cover
# ---------------------------------------------------------------------------
def latest_covered_date():
    latest = None
    for variable in WEATHER_VARIABLES:
        files = sorted(WEATHER_DIR.glob(f"{variable}_*.nc"))
        if not files:
            raise FileNotFoundError(f"No {variable}_*.nc files in {WEATHER_DIR}")
        with xr.open_dataset(files[-1]) as ds:
            day_max = pd.Timestamp(ds["day"].values.max())
        latest = day_max if latest is None else min(latest, day_max)
    return latest


latest_date = latest_covered_date()
decision_dates = pd.date_range(end=latest_date, periods=RECENT_DAYS, freq="D")
print("Scoring dates:", decision_dates.min().date(), "to", decision_dates.max().date())

# ---------------------------------------------------------------------------
# 3. Real FIRMS fire-history lag features (mirrors improved_model section 4/8)
# ---------------------------------------------------------------------------
years_needed = sorted({d.year for d in decision_dates} | {(decision_dates.min() - pd.Timedelta(days=14)).year})
fire_files = [FIRE_DIR / f"modis_fires_{y}.csv" for y in years_needed]
fire_files = [p for p in fire_files if p.exists()]
usecols = ["latitude", "longitude", "acq_date", "confidence", "frp", "brightness", "type"]
frames = [pd.read_csv(p, usecols=lambda c: c in usecols, low_memory=False) for p in fire_files]
fires = pd.concat(frames, ignore_index=True)
fires["date"] = pd.to_datetime(fires["acq_date"], errors="coerce").dt.normalize()
for col in ["latitude", "longitude", "confidence", "frp", "brightness", "type"]:
    if col in fires:
        fires[col] = pd.to_numeric(fires[col], errors="coerce")
fires = fires[
    fires["latitude"].between(24, 50)
    & fires["longitude"].between(-125, -66)
    & (fires["confidence"].fillna(0) >= CONFIDENCE_MIN)
].copy()
if "type" in fires and fires["type"].notna().any():
    fires = fires[fires["type"].fillna(0).eq(0)]

fires["lat_bin"] = np.floor(fires["latitude"] / GRID_DEG) * GRID_DEG
fires["lon_bin"] = np.floor(fires["longitude"] / GRID_DEG) * GRID_DEG
fires["grid_id"] = fires["lat_bin"].round(2).astype(str) + "_" + fires["lon_bin"].round(2).astype(str)
fires = fires[fires["grid_id"].isin(set(grid["grid_id"]))].copy()

daily_fire = (
    fires.groupby(["date", "grid_id"], as_index=False)
    .agg(fire_count=("frp", "size"), total_frp=("frp", "sum"))
)
history_source = daily_fire[["date", "grid_id", "fire_count", "total_frp"]].copy()

# ---------------------------------------------------------------------------
# 4. Assemble the dense inference table: every grid cell x every decision date
# ---------------------------------------------------------------------------
model_df = grid.assign(key=1).merge(
    pd.DataFrame({"date": decision_dates, "key": 1}), on="key"
).drop(columns="key")
model_df["year"] = model_df["date"].dt.year
model_df["month"] = model_df["date"].dt.month
model_df["dayofyear"] = model_df["date"].dt.dayofyear
model_df["sin_doy"] = np.sin(2 * np.pi * model_df["dayofyear"] / 366)
model_df["cos_doy"] = np.cos(2 * np.pi * model_df["dayofyear"] / 366)
print(f"{len(model_df):,} grid-cell x day rows to score")

for window in LAG_WINDOWS:
    count_total = np.zeros(len(model_df), dtype="float32")
    frp_total = np.zeros(len(model_df), dtype="float32")
    for lag in range(window):
        shifted = history_source.copy()
        shifted["date"] = shifted["date"] + pd.Timedelta(days=lag)
        shifted = shifted.rename(columns={"fire_count": f"_count_{lag}", "total_frp": f"_frp_{lag}"})
        model_df = model_df.merge(shifted, on=["date", "grid_id"], how="left")
        count_total += model_df.pop(f"_count_{lag}").fillna(0).to_numpy(dtype="float32")
        frp_total += model_df.pop(f"_frp_{lag}").fillna(0).to_numpy(dtype="float32")
    model_df[f"fire_count_lag_{window}d"] = count_total
    model_df[f"frp_lag_{window}d"] = frp_total

# ---------------------------------------------------------------------------
# 5. Real gridMET weather (mirrors improved_model section 5)
# ---------------------------------------------------------------------------
def extract_gridmet(points, variable, year, chunk_size=200_000):
    path = WEATHER_DIR / f"{variable}_{year}.nc"
    pieces = []
    with xr.open_dataset(path, decode_times=True, mask_and_scale=True) as ds:
        data_vars = [name for name in ds.data_vars if name != "crs"]
        da = ds[data_vars[0]]
        for start in range(0, len(points), chunk_size):
            block = points.iloc[start:start + chunk_size]
            selected = da.sel(
                day=xr.DataArray(block["date"].to_numpy(), dims="points"),
                lat=xr.DataArray(block["lat"].to_numpy(), dims="points"),
                lon=xr.DataArray(block["lon"].to_numpy(), dims="points"),
                method="nearest",
            )
            pieces.append(np.asarray(selected.values, dtype="float32"))
    values = np.concatenate(pieces)
    if variable in {"tmmx", "tmmn"}:
        values = values - 273.15
    return values


for variable in WEATHER_VARIABLES:
    model_df[variable] = np.nan
    for year, index in model_df.groupby("year").groups.items():
        block = model_df.loc[index, ["date", "lat", "lon"]]
        model_df.loc[index, variable] = extract_gridmet(block, variable, int(year))
    print(variable, f"missing={model_df[variable].isna().mean():.3%}")

before = len(model_df)
model_df = model_df.dropna(subset=WEATHER_VARIABLES).reset_index(drop=True)
print(f"Dropped {before - len(model_df):,} rows outside GridMET land coverage")

# ---------------------------------------------------------------------------
# 6. Run the REAL trained model (uses the notebook's own inference contract)
# ---------------------------------------------------------------------------
missing = sorted(set(feature_cols) - set(model_df.columns))
if missing:
    raise ValueError(f"Assembled table is missing model features: {missing}")

probability = bundle["estimator"].predict_proba(model_df[feature_cols])[:, 1]
model_df["ignition_candidate_probability"] = probability
model_df["watch_recall_80"] = probability >= bundle["thresholds"]["recall_80"]
model_df["watch_alert_budget"] = probability >= bundle["thresholds"]["alert_budget_5pct"]

export_cols = (
    ["date", "grid_id", "lat", "lon"]
    + feature_cols
    + ["ignition_candidate_probability", "watch_recall_80", "watch_alert_budget"]
)
model_df[export_cols].to_csv(OUT_FILE, index=False, compression="gzip")
print("Wrote", OUT_FILE, f"({OUT_FILE.stat().st_size / 1024**2:.1f} MB), {len(model_df):,} rows")
print("Done. This file is inside the folder already shared with Claude -- nothing else to do.")
