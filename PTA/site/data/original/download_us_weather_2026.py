"""
Download 2026 US weather data from Open-Meteo, gridded across the continental US.

Requires: pip install requests
Run: python download_us_weather_2026.py

Output: us_weather_2026_grid.csv with columns:
  latitude, longitude, date, temperature_2m_max, temperature_2m_min, precipitation_sum

Notes:
- Open-Meteo's free tier allows up to 10,000 calls/day, no API key needed.
- This script uses a 1-degree grid over the continental US bounding box
  (lat 25-49, lon -125 to -67) => ~900 points. Ocean points will simply
  return marine-adjacent weather (harmless, easy to filter out later by
  lat/lon if you only want strict land coverage).
- A ~0.2s delay between calls keeps you well under rate limits; the full
  run takes roughly 15-20 minutes for ~900 points x ~180 days each.
- To narrow scope (faster/smaller), reduce GRID_STEP (e.g. 2.0 for a
  coarser grid) or shrink the bounding box below.
"""

import csv
import time
import requests

# ---- Configuration ----
LAT_MIN, LAT_MAX = 25.0, 49.0
LON_MIN, LON_MAX = -125.0, -67.0
GRID_STEP = 1.0  # degrees; increase to 2.0 or 3.0 for a faster/coarser run

START_DATE = "2026-01-01"
END_DATE = "2026-07-01"  # adjust as needed; Open-Meteo will cap at latest available date

DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum"
OUTPUT_FILE = "us_weather_2026_grid.csv"
API_URL = "https://archive-api.open-meteo.com/v1/archive"

# ---- Build grid points ----
def frange(start, stop, step):
    vals = []
    v = start
    while v <= stop + 1e-9:
        vals.append(round(v, 2))
        v += step
    return vals

lats = frange(LAT_MIN, LAT_MAX, GRID_STEP)
lons = frange(LON_MIN, LON_MAX, GRID_STEP)
grid_points = [(lat, lon) for lat in lats for lon in lons]

print(f"Total grid points: {len(grid_points)}")

# ---- Fetch and write ----
with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["latitude", "longitude", "date", "temperature_2m_max",
                      "temperature_2m_min", "precipitation_sum"])

    for i, (lat, lon) in enumerate(grid_points, 1):
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "daily": DAILY_VARS,
            "timezone": "auto",
        }
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            precip = daily.get("precipitation_sum", [])

            for d, mx, mn, p in zip(dates, tmax, tmin, precip):
                writer.writerow([lat, lon, d, mx, mn, p])

            print(f"[{i}/{len(grid_points)}] lat={lat}, lon={lon} -> {len(dates)} days OK")

        except Exception as e:
            print(f"[{i}/{len(grid_points)}] lat={lat}, lon={lon} -> FAILED: {e}")

        time.sleep(0.2)  # be polite to the free API

print(f"\nDone. Data written to {OUTPUT_FILE}")
