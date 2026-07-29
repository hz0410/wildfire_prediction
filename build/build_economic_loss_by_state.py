"""
Compile a per-state, per-year wildfire economic-loss table (2020-2026) to sit
alongside the fires-by-state choropleth. Source: NOAA/NCEI Storm Events wildfire
records already compiled for the notebook's economic-loss model
(data/noaa_wildfire_economic_impacts_2020_2026.csv). Values are the sum of
NOAA-reported property + crop damage (nominal USD) for events beginning in a
given state and year. States with no NOAA-reported wildfire-damage record in a
year are 0, not missing -- NOAA Storm Events only captures events an observer
chose to report with a dollar estimate, so 0 means "no reported damage found",
not "no fire risk".
"""
import json
from pathlib import Path

import pandas as pd

ADV = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/website')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/data')

# Same 50-state list/order as fires_by_state.json, built from the same
# STATE_ABBR_TO_NAME source used there.
ALL_STATES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
    'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
    'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
    'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
    'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
    'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
    'Wisconsin', 'Wyoming',
]
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

df = pd.read_csv(ADV / 'data' / 'noaa_wildfire_economic_impacts_2020_2026.csv', low_memory=False)
df['STATE_TITLE'] = df['STATE'].astype(str).str.strip().str.title()
df['total_reported_damage_usd'] = pd.to_numeric(df['total_reported_damage_usd'], errors='coerce').fillna(0.0)

agg = (
    df[df['STATE_TITLE'].isin(ALL_STATES)]
    .groupby(['STATE_TITLE', 'YEAR'])['total_reported_damage_usd']
    .sum()
)

states_out = {}
for state in ALL_STATES:
    entry = {}
    for y in YEARS:
        entry[str(y)] = float(agg.get((state, y), 0.0))
    states_out[state] = entry

national_totals = {
    y: float(sum(states_out[s][str(y)] for s in ALL_STATES))
    for y in YEARS
}

# Which states/territories in the raw NOAA data were excluded from the map
# (out-of-CONUS-50 rows -- e.g. Puerto Rico, Guam -- not silently dropped).
excluded = sorted(set(df['STATE_TITLE'].unique()) - set(ALL_STATES))

result = {
    "years": YEARS,
    "metric": "noaa_reported_property_plus_crop_damage_usd",
    "national_totals": national_totals,
    "states": states_out,
    "excluded_non_state_records": excluded,
    "sources": {
        "noaa_reported_property_plus_crop_damage_usd": (
            "NOAA/NCEI Storm Events Database, EVENT_TYPE='Wildfire' records, "
            "2020-2026, summed DAMAGE_PROPERTY + DAMAGE_CROPS per state per year "
            "(nominal USD, not inflation-adjusted). Same source table used by this "
            "project's notebook economic-loss model."
        ),
    },
    "note": (
        "A state showing $0 means NOAA Storm Events has no reported-damage wildfire "
        "record for that state and year, not that no fires or damage occurred there -- "
        "NOAA Storm Events relies on what local offices chose to report with a dollar "
        "estimate, so this systematically undercounts true economic loss, especially in "
        "states/years without a single catastrophic, heavily-covered fire. 2026 is a "
        "partial year through late July."
    ),
}

with open(OUT / 'economic_loss_by_state.json', 'w') as f:
    json.dump(result, f, indent=1)

print('Saved economic_loss_by_state.json with', len(ALL_STATES), 'states x', len(YEARS), 'years')
print('excluded non-CONUS-50 records from:', excluded)
for y in YEARS:
    print(y, 'national total reported damage $:', f"{national_totals[y]:,.0f}")
