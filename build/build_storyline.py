import json
from pathlib import Path

DATA = Path('/sessions/gallant-festive-albattani/mnt/outputs/site_build/data')
DATA.mkdir(exist_ok=True)

# Source: National Interagency Coordination Center / NIFC, "Total Wildland Fires
# and Acres" (1983-2025) https://www.nifc.gov/fire-information/statistics/wildfires
nifc_fires_acres = {
    2025: (77850, 5131474), 2024: (64897, 8924884), 2023: (56580, 2693910),
    2022: (68988, 7577183), 2021: (58985, 7125643), 2020: (58950, 10122336),
    2019: (50477, 4664364), 2018: (58083, 8767492), 2017: (71499, 10026086),
    2016: (67743, 5509995), 2015: (68151, 10125149), 2014: (63312, 3595613),
    2013: (47579, 4319546), 2012: (67774, 9326238), 2011: (74126, 8711367),
    2010: (71971, 3422724), 2009: (78792, 5921786), 2008: (78979, 5292468),
    2007: (85705, 9328045), 2006: (96385, 9873745), 2005: (66753, 8689389),
    2004: (65461, 8097880), 2003: (63629, 3960842), 2002: (73457, 7184712),
    2001: (84079, 3570911), 2000: (92250, 7393493), 1999: (92487, 5626093),
    1998: (81043, 1329704), 1997: (66196, 2856959), 1996: (96363, 6065998),
    1995: (82234, 1840546), 1994: (79107, 4073579), 1993: (58810, 1797574),
    1992: (87394, 2069929), 1991: (75754, 2953578), 1990: (66481, 4621621),
    1989: (48949, 1827310), 1988: (72750, 5009290), 1987: (71300, 2447296),
    1986: (85907, 2719162), 1985: (82591, 2896147), 1984: (20493, 1148409),
    1983: (18229, 1323666),
}

# Source: NIFC "Human-caused wildfires" (total column, 2001-2025)
# https://www.nifc.gov/fire-information/statistics/human-caused
nifc_human_caused = {
    2025: 69556, 2024: 57962, 2023: 50697, 2022: 61429, 2021: 52641,
    2020: 53563, 2019: 44115, 2018: 51576, 2017: 63546, 2016: 60932,
    2015: 58916, 2014: 55679, 2013: 38349, 2012: 58331, 2011: 63877,
    2010: 64807, 2009: 69650, 2008: 70093, 2007: 73446, 2006: 80220,
    2005: 58430, 2004: 54101, 2003: 50815, 2002: 62022, 2001: 71456,
}

annual = []
for year in sorted(nifc_fires_acres.keys()):
    fires, acres = nifc_fires_acres[year]
    human = nifc_human_caused.get(year)
    annual.append({
        'year': year,
        'fires': fires,
        'acres': acres,
        'human_caused_fires': human,
        'human_caused_pct': round(100 * human / fires, 1) if human else None,
    })

with open(DATA / 'annual_stats.json', 'w') as f:
    json.dump({
        'source': 'National Interagency Coordination Center / NIFC',
        'source_url': 'https://www.nifc.gov/fire-information/statistics/wildfires',
        'note': (
            'Nationwide wildfire totals compiled from federal/state Situation '
            'Reports since 1983 (no official pre-1983 data). This differs from '
            'the PTA model, which trains only on Jan-Jun 2026 satellite and '
            'incident-perimeter data for the interactive map below.'
        ),
        'annual': annual,
    }, f, indent=1)

big_fires = [
    {
        'name': 'August Complex', 'year': 2020, 'state': 'California',
        'acres': 1032648, 'deaths': 0, 'structures_destroyed': 935,
        'cost_usd': None, 'cause': 'Lightning (38 separate ignitions merged into one complex)',
        'blurb': (
            "The first fire in modern California history to top 1 million acres "
            "-- a \"gigafire.\" Started from a mid-August lightning siege across "
            "six Northern California counties."
        ),
        'source': 'https://en.wikipedia.org/wiki/August_Complex_fire',
    },
    {
        'name': 'Dixie Fire', 'year': 2021, 'state': 'California',
        'acres': 963309, 'deaths': 0, 'structures_destroyed': 1311,
        'cost_usd': 637400000, 'cause': 'Tree contacting a PG&E power line',
        'blurb': (
            "California's largest single-ignition-point fire on record, and the "
            "costliest to suppress in U.S. history. Nearly destroyed the town of "
            "Greenville."
        ),
        'source': 'https://en.wikipedia.org/wiki/Dixie_Fire',
    },
    {
        'name': 'Camp Fire', 'year': 2018, 'state': 'California',
        'acres': 153336, 'deaths': 85, 'structures_destroyed': 18804,
        'cost_usd': 16500000000, 'cause': 'Failed PG&E transmission line hardware',
        'blurb': (
            "The deadliest and most destructive wildfire in California history. "
            "Nearly destroyed the town of Paradise in a matter of hours."
        ),
        'source': 'https://en.wikipedia.org/wiki/Camp_Fire_(2018)',
    },
    {
        'name': 'Lahaina / Maui Fires', 'year': 2023, 'state': 'Hawaii',
        'acres': 2170, 'deaths': 102, 'structures_destroyed': 2200,
        'cost_usd': None, 'cause': 'Reenergized downed power line igniting dry grass',
        'blurb': (
            "Tiny by acreage but the deadliest U.S. wildfire in over a century, "
            "driven by hurricane-enhanced winds through the historic town of "
            "Lahaina -- a reminder that acres burned and human cost are not the "
            "same thing."
        ),
        'source': 'https://en.wikipedia.org/wiki/2023_Hawaii_wildfires',
    },
    {
        'name': 'Marshall Fire', 'year': 2021, 'state': 'Colorado',
        'acres': 6080, 'deaths': 2, 'structures_destroyed': 1084,
        'cost_usd': 2000000000, 'cause': 'Smoldering embers + a sparking power line, in hurricane-force wind',
        'blurb': (
            "Colorado's most destructive fire ever, burning through suburban "
            "neighborhoods in winter -- proof that wildfire risk isn't confined "
            "to summer or to forested land."
        ),
        'source': 'https://en.wikipedia.org/wiki/Marshall_Fire',
    },
    {
        'name': 'Wallow Fire', 'year': 2011, 'state': 'Arizona',
        'acres': 538049, 'deaths': 0, 'structures_destroyed': 72,
        'cost_usd': None, 'cause': 'Human-caused (abandoned campfire)',
        'blurb': "Arizona's largest wildfire on record at the time, burning across the White Mountains.",
        'source': 'https://en.wikipedia.org/wiki/Wallow_Fire',
    },
    {
        'name': 'Rodeo-Chediski Fire', 'year': 2002, 'state': 'Arizona',
        'acres': 468638, 'deaths': 0, 'structures_destroyed': 491,
        'cost_usd': None, 'cause': 'Human-caused (signal fire + arson, two fires merged)',
        'blurb': "The largest fire in Arizona history until Wallow surpassed it nine years later.",
        'source': 'https://en.wikipedia.org/wiki/Rodeo%E2%80%93Chediski_Fire',
    },
    {
        'name': 'Biscuit Fire', 'year': 2002, 'state': 'Oregon',
        'acres': 499965, 'deaths': 0, 'structures_destroyed': 0,
        'cost_usd': None, 'cause': 'Lightning',
        'blurb': "Oregon's largest recorded wildfire, burning largely in remote Kalmiopsis wilderness.",
        'source': 'https://en.wikipedia.org/wiki/Biscuit_Fire',
    },
]

with open(DATA / 'big_fires.json', 'w') as f:
    json.dump(big_fires, f, indent=1)

print('Wrote annual_stats.json (%d years) and big_fires.json (%d cases)' % (len(annual), len(big_fires)))
