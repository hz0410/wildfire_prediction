"""Download the official USGS National Structures fire/EMS station layer."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER_URL = "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer/16/query"
OUTPUT = Path(__file__).with_name("usgs_fire_ems_stations.geojson")
PAGE_SIZE = 2000


def main() -> None:
    features = []
    offset = 0
    while True:
        query = urlencode({
            "where": "1=1",
            "outFields": "OBJECTID,NAME,STATE,ADMINTYPE,POINTLOCATIONTYPE",
            "outSR": "4326",
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "orderByFields": "OBJECTID",
            "f": "geojson",
        })
        request = Request(f"{LAYER_URL}?{query}", headers={"User-Agent": "PTA-Wildfire-Research/1.0"})
        with urlopen(request, timeout=90) as response:
            page = json.load(response)
        batch = page.get("features", [])
        features.extend(batch)
        print(f"Downloaded {len(features):,} stations")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    collection = {
        "type": "FeatureCollection",
        "name": "USGS National Structures Fire Stations EMS Stations",
        "source": LAYER_URL,
        "features": features,
    }
    OUTPUT.write_text(json.dumps(collection), encoding="utf-8")
    print(f"Saved {len(features):,} records to {OUTPUT}")


if __name__ == "__main__":
    main()
