"""
Build two small client-side lookup files so the address-lookup report
(index.html Section 05) can cite real, state-level economic-loss context for
whatever grid cell an address falls in:

1. data/cell_to_state.json -- maps this project's 1-degree parent grid_id
   (the same "{lat}_{lon}" key already used in data/grid_index.json) to a
   full state name, built from the human-activity CSV's state-prefixed
   grid_id (e.g. "TX_25.0_-98.0" -> parent grid_id "25.0_-98.0" -> "Texas").

2. data/economic_loss_state_summary.json -- per-state NOAA Storm Events
   wildfire economic-loss summary stats (2020-2025, provisional 2026
   excluded): average annual total reported damage, median per-incident
   damage among incidents with positive reported damage, and the share of
   records with any positive reported damage. Same source CSV as the
   notebook's economic-loss model and the state choropleth's loss layer.
"""
import json
from pathlib import Path

import pandas as pd

ADV = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta/website')
OUT = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_v2/data')

STATE_ABBR_TO_NAME = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
    'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
    'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}

# ---------------------------------------------------------------------------
# 1) cell -> state lookup. data/grid_index.json's grid_id is a 0.25-degree
# subcell ("{lat_bin}_{lon_bin}", e.g. "25.5_-98.0"), but the human-activity
# CSV's state prefix is only known at the 1-degree PARENT cell ("TX_25.0_
# -98.0"). Floor each subcell down to its parent (same approach used to bin
# FIRMS points to states in build_fires_by_state.py) so every one of
# grid_index.json's 12,160 subcells resolves to a state, not just the ~800
# that happen to sit exactly on a parent-cell corner.
# ---------------------------------------------------------------------------
human = pd.read_csv(ADV.parent / 'data' / 'human_activity' / 'grid_human_activity_features.csv')
parts = human['grid_id'].str.split('_', n=1, expand=True)
human['state_abbr'] = parts[0]
human['parent_key'] = parts[1]  # "{lat}_{lon}" of the 1-degree parent cell
human = human[human['state_abbr'].isin(STATE_ABBR_TO_NAME)]

# Some 1-degree parent cells are claimed by more than one state in this CSV
# (legitimate border-straddling cells -- confirmed e.g. "39.0_-77.0" appears
# as both MD_39.0_-77.0 and PA_39.0_-77.0 with identical population/road
# data). A naive "last row wins" dict silently resolves these arbitrarily --
# confirmed wrong for Baltimore, MD, which resolved to Pennsylvania. Instead,
# collect every candidate state per parent cell, and when a cell is
# ambiguous, break the tie in favor of whichever state has FEWER total
# assigned cells in this CSV: smaller states have less margin to lose a
# border cell to a larger neighbor, so this is a more defensible default
# than file order. Ties on cell count are broken alphabetically for
# determinism.
state_cell_counts = human.groupby('state_abbr')['parent_key'].nunique().to_dict()

parent_to_states = {}
for row in human.itertuples():
    parent_to_states.setdefault(row.parent_key, set()).add(row.state_abbr)

parent_to_state = {}
ambiguous_count = 0
for parent_key, abbrs in parent_to_states.items():
    if len(abbrs) > 1:
        ambiguous_count += 1
        chosen = min(abbrs, key=lambda a: (state_cell_counts.get(a, 0), a))
    else:
        chosen = next(iter(abbrs))
    parent_to_state[parent_key] = STATE_ABBR_TO_NAME[chosen]

print(f'{ambiguous_count} of {len(parent_to_states)} parent cells are claimed by '
      f'more than one state; resolved each to its smaller-state candidate.')

import numpy as np

with open(OUT / 'grid_index.json') as f:
    grid_index = json.load(f)

cell_to_state = {}
unmatched = 0
for cell in grid_index:
    # round first to guard against float artifacts (e.g. 25.7499999999)
    # before flooring to the 1-degree parent cell -- np.floor rounds toward
    # -infinity, which is what we want for negative longitudes too.
    parent_lat = np.floor(round(float(cell['lat_bin']), 3))
    parent_lon = np.floor(round(float(cell['lon_bin']), 3))
    parent_key = f"{parent_lat:.1f}_{parent_lon:.1f}"
    state = parent_to_state.get(parent_key)
    if state:
        cell_to_state[cell['grid_id']] = state
    else:
        unmatched += 1

with open(OUT / 'cell_to_state.json', 'w') as f:
    json.dump(cell_to_state, f)
print('Saved cell_to_state.json with', len(cell_to_state), 'of', len(grid_index), 'cells matched;', unmatched, 'unmatched')

# ---------------------------------------------------------------------------
# 2) per-state economic summary stats, 2020-2025 (2026 excluded, partial year)
# ---------------------------------------------------------------------------
df = pd.read_csv(ADV / 'data' / 'noaa_wildfire_economic_impacts_2020_2026.csv', low_memory=False)
df = df[df['YEAR'].between(2020, 2025)].copy()
df['STATE_TITLE'] = df['STATE'].astype(str).str.strip().str.title()
df['total_reported_damage_usd'] = pd.to_numeric(df['total_reported_damage_usd'], errors='coerce')
df['damage_reported'] = df['damage_reported'].astype(bool)

summary = {}
for state, group in df.groupby('STATE_TITLE'):
    reported = group[group['damage_reported']]
    positive = reported[reported['total_reported_damage_usd'] > 0]
    summary[state] = {
        "avg_annual_reported_damage_usd": float(reported['total_reported_damage_usd'].fillna(0).sum() / 6),
        "median_positive_incident_damage_usd": (
            float(positive['total_reported_damage_usd'].median()) if len(positive) else None
        ),
        "positive_incident_count": int(len(positive)),
        "reported_incident_count": int(len(reported)),
    }

with open(OUT / 'economic_loss_state_summary.json', 'w') as f:
    json.dump({
        "years": [2020, 2021, 2022, 2023, 2024, 2025],
        "states": summary,
        "note": (
            "median_positive_incident_damage_usd is the median NOAA-reported "
            "property+crop damage among that state's wildfire records with "
            "positive reported damage, 2020-2025 pooled (per-state-year counts "
            "are too small individually to report a stable median). null means "
            "the state had zero NOAA-reported positive-damage wildfire records "
            "in this window, not that no damage occurred."
        ),
        "source": "NOAA/NCEI Storm Events Database, EVENT_TYPE='Wildfire', 2020-2025.",
    }, f, indent=1)
print('Saved economic_loss_state_summary.json for', len(summary), 'states')
