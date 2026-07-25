"""
Compile a per-state, per-year wildfire count table (2020-2026) for the
choropleth map section. 2020-2025 come from NIFC's official annual
"Wildland Fires and Acres Burned by State and Agency" report tables
(state Fires-Total row), transcribed from the published PDFs. 2026 has no
NIFC annual report yet (year in progress), so it's built the same way the
rest of this site's "current year" data is: binning real 2026 FIRMS
satellite detections onto the human-activity grid's state field.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ADV = Path('/sessions/gallant-festive-albattani/mnt/advanced_pta')
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

# NIFC official annual report state Fires-Total figures, transcribed from
# nifc.gov "Wildland Fire Summary and Statistics Annual Report" PDFs, 2020-2025
NIFC_STATE_FIRES = {
2020: {"Alabama": 836, "Alaska": 349, "Arizona": 2524, "Arkansas": 655, "California": 10431, "Colorado": 1080, "Connecticut": 586, "Delaware": 426, "Florida": 2381, "Georgia": 1699, "Hawaii": 58, "Idaho": 944, "Illinois": 19, "Indiana": 11, "Iowa": 126, "Kansas": 52, "Kentucky": 524, "Louisiana": 401, "Maine": 1156, "Maryland": 2, "Massachusetts": 1189, "Michigan": 409, "Minnesota": 1372, "Mississippi": 1090, "Missouri": 1090, "Montana": 2433, "Nebraska": 41, "Nevada": 770, "New Hampshire": 252, "New Jersey": 1981, "New Mexico": 1018, "New York": 192, "North Carolina": 2364, "North Dakota": 651, "Ohio": 649, "Oklahoma": 1241, "Oregon": 2215, "Pennsylvania": 1488, "Rhode Island": 113, "South Carolina": 465, "South Dakota": 852, "Tennessee": 550, "Texas": 6713, "Utah": 1493, "Vermont": 96, "Virginia": 410, "Washington": 1646, "West Virginia": 1230, "Wisconsin": 781, "Wyoming": 828},
2021: {"Alabama": 1040, "Alaska": 384, "Arizona": 1773, "Arkansas": 378, "California": 9280, "Colorado": 1017, "Connecticut": 60, "Delaware": 0, "Florida": 2262, "Georgia": 2139, "Hawaii": 1, "Idaho": 1332, "Illinois": 29, "Indiana": 34, "Iowa": 187, "Kansas": 55, "Kentucky": 723, "Louisiana": 507, "Maine": 636, "Maryland": 112, "Massachusetts": 588, "Michigan": 435, "Minnesota": 2065, "Mississippi": 922, "Missouri": 1531, "Montana": 2573, "Nebraska": 785, "Nevada": 565, "New Hampshire": 280, "New Jersey": 906, "New Mexico": 672, "New York": 137, "North Carolina": 5151, "North Dakota": 946, "Ohio": 524, "Oklahoma": 1727, "Oregon": 2202, "Pennsylvania": 1350, "Rhode Island": 99, "South Carolina": 630, "South Dakota": 868, "Tennessee": 550, "Texas": 5576, "Utah": 1085, "Vermont": 90, "Virginia": 567, "Washington": 1863, "West Virginia": 752, "Wisconsin": 1040, "Wyoming": 540},
2022: {"Alabama": 2710, "Alaska": 595, "Arizona": 1432, "Arkansas": 1903, "California": 7884, "Colorado": 835, "Connecticut": 150, "Delaware": 7, "Florida": 2784, "Georgia": 3621, "Hawaii": 5, "Idaho": 1088, "Illinois": 32, "Indiana": 49, "Iowa": 7, "Kansas": 67, "Kentucky": 1280, "Louisiana": 1259, "Maine": 730, "Maryland": 117, "Massachusetts": 1192, "Michigan": 376, "Minnesota": 713, "Mississippi": 1980, "Missouri": 136, "Montana": 2087, "Nebraska": 568, "Nevada": 506, "New Hampshire": 103, "New Jersey": 1165, "New Mexico": 748, "New York": 162, "North Carolina": 6222, "North Dakota": 111, "Ohio": 724, "Oklahoma": 2811, "Oregon": 2117, "Pennsylvania": 951, "Rhode Island": 76, "South Carolina": 22, "South Dakota": 527, "Tennessee": 1225, "Texas": 12571, "Utah": 945, "Vermont": 86, "Virginia": 558, "Washington": 1492, "West Virginia": 893, "Wisconsin": 923, "Wyoming": 443},
2023: {"Alabama": 1856, "Alaska": 346, "Arizona": 1837, "Arkansas": 147, "California": 7364, "Colorado": 861, "Connecticut": 499, "Delaware": 1, "Florida": 2730, "Georgia": 2386, "Hawaii": 214, "Idaho": 892, "Illinois": 22, "Indiana": 47, "Iowa": 6, "Kansas": 49, "Kentucky": 9, "Louisiana": 1467, "Maine": 493, "Maryland": 196, "Massachusetts": 1079, "Michigan": 466, "Minnesota": 836, "Mississippi": 2383, "Missouri": 127, "Montana": 1662, "Nebraska": 569, "Nevada": 375, "New Hampshire": 52, "New Jersey": 1194, "New Mexico": 1019, "New York": 150, "North Carolina": 5214, "North Dakota": 471, "Ohio": 883, "Oklahoma": 1580, "Oregon": 1979, "Pennsylvania": 1910, "Rhode Island": 78, "South Carolina": 22, "South Dakota": 177, "Tennessee": 772, "Texas": 7102, "Utah": 782, "Vermont": 67, "Virginia": 43, "Washington": 1707, "West Virginia": 1124, "Wisconsin": 1086, "Wyoming": 249},
2024: {"Alabama": 1525, "Alaska": 377, "Arizona": 2191, "Arkansas": 1219, "California": 8316, "Colorado": 894, "Connecticut": 356, "Delaware": 23, "Florida": 2348, "Georgia": 2492, "Hawaii": 90, "Idaho": 1450, "Illinois": 47, "Indiana": 64, "Iowa": 362, "Kansas": 41, "Kentucky": 957, "Louisiana": 385, "Maine": 653, "Maryland": 174, "Massachusetts": 1299, "Michigan": 447, "Minnesota": 1123, "Mississippi": 1800, "Missouri": 2804, "Montana": 2323, "Nebraska": 1035, "Nevada": 929, "New Hampshire": 130, "New Jersey": 1443, "New Mexico": 823, "New York": 125, "North Carolina": 4668, "North Dakota": 935, "Ohio": 1107, "Oklahoma": 3041, "Oregon": 2232, "Pennsylvania": 1448, "Rhode Island": 73, "South Carolina": 50, "South Dakota": 675, "Tennessee": 596, "Texas": 4967, "Utah": 1211, "Vermont": 97, "Virginia": 742, "Washington": 1806, "West Virginia": 1104, "Wisconsin": 1162, "Wyoming": 738},
2025: {"Alabama": 1861, "Alaska": 465, "Arizona": 1593, "Arkansas": 194, "California": 9002, "Colorado": 1123, "Connecticut": 256, "Delaware": 15, "Florida": 3704, "Georgia": 4048, "Hawaii": 9, "Idaho": 1302, "Illinois": 40, "Indiana": 30, "Iowa": 3173, "Kansas": 37, "Kentucky": 758, "Louisiana": 861, "Maine": 856, "Maryland": 176, "Massachusetts": 1158, "Michigan": 516, "Minnesota": 1381, "Mississippi": 1821, "Missouri": 1672, "Montana": 2431, "Nebraska": 511, "Nevada": 568, "New Hampshire": 157, "New Jersey": 1323, "New Mexico": 907, "New York": 203, "North Carolina": 6925, "North Dakota": 409, "Ohio": 560, "Oklahoma": 2537, "Oregon": 2746, "Pennsylvania": 1546, "Rhode Island": 62, "South Carolina": 71, "South Dakota": 458, "Tennessee": 842, "Texas": 5839, "Utah": 1093, "Vermont": 106, "Virginia": 7709, "Washington": 1874, "West Virginia": 14, "Wisconsin": 1284, "Wyoming": 505},
}
NIFC_NATIONAL_TOTALS = {
    # 2020-2022 cross-checked against NIFC's separate "Federal Firefighting Costs"
    # table (nifc.gov/sites/default/files/document-media/SuppCosts.pdf), which
    # independently confirms 2020/2021/2022 fires+acres exactly. The 2021 value
    # in this project's earlier PDF extraction of the 2021 annual report
    # mistakenly picked up 2022's benchmark figure (68,988) instead of 2021's
    # own (58,985) -- corrected here using the cross-checked source.
    2020: {"fires": 58950, "acres": 10122336},
    2021: {"fires": 58985, "acres": 7125643},
    2022: {"fires": 68988, "acres": 7577183},
    2023: {"fires": 56580, "acres": 2693910},
    2024: {"fires": 64897, "acres": 8924884},
    2025: {"fires": 77850, "acres": 5131474},
}

# ---------------------------------------------------------------------------
# 2026: no NIFC annual report yet -> bin real 2026 FIRMS detections by state,
# using the same state field already present in the human-activity grid CSV.
# ---------------------------------------------------------------------------
human = pd.read_csv(ADV / 'data' / 'human_activity' / 'grid_human_activity_features.csv')
parts = human['grid_id'].str.rsplit('_', n=2, expand=True)
human['state_abbr'] = parts[0]
human['parent_lat'] = pd.to_numeric(parts[1], errors='coerce')
human['parent_lon'] = pd.to_numeric(parts[2], errors='coerce')
cell_state = human.groupby(['parent_lat', 'parent_lon'])['state_abbr'].first().to_dict()

fires = pd.read_csv(ADV / 'new_data' / 'firms' / 'modis_fires_2026.csv', low_memory=False,
                     usecols=['latitude', 'longitude', 'confidence', 'type'])
fires = fires[fires['confidence'] >= 30]
if fires['type'].notna().any():
    fires = fires[fires['type'].fillna(0).eq(0)]
fires = fires[fires['latitude'].between(24, 50) & fires['longitude'].between(-125, -66)]
fires['lat_bin1'] = np.floor(fires['latitude'])
fires['lon_bin1'] = np.floor(fires['longitude'])
fires['state_abbr'] = list(map(lambda t: cell_state.get(t), zip(fires['lat_bin1'], fires['lon_bin1'])))
fires_2026_by_state_abbr = fires.dropna(subset=['state_abbr'])['state_abbr'].value_counts().to_dict()
fires_2026_by_state = {
    STATE_ABBR_TO_NAME[abbr]: int(n)
    for abbr, n in fires_2026_by_state_abbr.items()
    if abbr in STATE_ABBR_TO_NAME
}
print('2026 FIRMS detections binned to', len(fires_2026_by_state), 'states, total', sum(fires_2026_by_state.values()))

# ---------------------------------------------------------------------------
# Assemble final structure
# ---------------------------------------------------------------------------
all_states = sorted(STATE_ABBR_TO_NAME.values())
years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
states_out = {}
for state in all_states:
    entry = {}
    for y in years:
        if y == 2026:
            entry[str(y)] = fires_2026_by_state.get(state, 0)
        else:
            entry[str(y)] = NIFC_STATE_FIRES[y].get(state, 0)
    states_out[state] = entry

result = {
    "years": years,
    "metric_by_year": {
        "2020": "reported_fires_nifc", "2021": "reported_fires_nifc", "2022": "reported_fires_nifc",
        "2023": "reported_fires_nifc", "2024": "reported_fires_nifc", "2025": "reported_fires_nifc",
        "2026": "satellite_detections_firms",
    },
    "national_totals": NIFC_NATIONAL_TOTALS,
    "states": states_out,
    "sources": {
        "reported_fires_nifc": "NIFC National Interagency Coordination Center, 'Wildland Fire Summary and Statistics Annual Report', state-by-state 'Wildland Fires and Acres Burned by State and Agency' table (SIT/209 Application figures), 2020-2025 editions.",
        "satellite_detections_firms": "NASA FIRMS MODIS/VIIRS active-fire detections, confidence >= 30, vegetation fires, binned to state via this project's human-activity grid. 2026 is a partial year (through late July) and NOT directly comparable in methodology to the NIFC-reported years -- it counts satellite hotspot detections, not officially reported incidents, and a single fire can register many detections.",
    },
    "note": "NIFC's per-state SIT/209 table total does not always exactly match NIFC's separately-published national benchmark total for the same year (the state table only reflects specific reporting agencies covered by SIT/209 reporting); both are shown as published, and the gap is normal, not an error.",
}

with open(OUT / 'fires_by_state.json', 'w') as f:
    json.dump(result, f, indent=1)
print('Saved fires_by_state.json with', len(all_states), 'states x', len(years), 'years')

# sanity check totals
for y in years:
    total = sum(states_out[s][str(y)] for s in all_states)
    print(y, 'sum of state totals:', total)
