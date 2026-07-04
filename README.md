# PTA Wildfire Risk Site

A static, scrollytelling wildfire site: national fire/acreage trends, big-fire
case studies, and an interactive U.S. address lookup backed by a random-forest
model trained on your 2026 PTA data.

## How to open it

This is a plain static site (`index.html` + `css/` + `js/` + `data/`), so it
needs to be served over HTTP rather than opened directly as a `file://` URL
(the browser blocks `fetch()` of local JSON files under `file://`). Easiest
options:

- **VS Code**: install the "Live Server" extension, right-click `index.html`, "Open with Live Server".
- **Terminal**: `cd` into this folder and run `python3 -m http.server 8000`, then visit `http://localhost:8000`.
- **Deploy**: push this folder to a GitHub repo and enable GitHub Pages (same setup as the reference template).

An internet connection is needed at view-time for: the U.S. Census geocoder
(address -> lat/lon, free, no key), map tiles, and the Chart.js/Leaflet CDN
scripts. Everything else (the trained model, all 2026 data) is bundled in
`data/` and runs entirely in the browser.

## What's real vs. approximated

- **National fires-per-year / acres-per-year charts**: real NIFC statistics, 1983-2025.
- **Big fire case studies**: real, individually verified (Wikipedia/CAL FIRE/NPR/etc. -- sources linked on each card).
- **Address lookup, dates on or before 2026-06-26**: real observed 2026 MODIS satellite detections and reported fire-incident data (ground truth, not a prediction).
- **Address lookup, dates after 2026-06-26**: a random-forest model (60 trees, trained on this repo's real 2026 fire + weather panel; holdout ROC AUC ~0.82) predicts next-day fire probability and scale. Because there's no real future weather forecast in this dataset, future weather is estimated from a day-of-year seasonal fit rather than an actual forecast, and fire-history features assume no new fires occur between the data cutoff and the requested date. This is documented in the UI itself.
- **1km circle on the map**: shows the requested location; the underlying model resolution is a 1-degree (~111km) grid cell, so this is the "nearest modeled area," not a literal 1km-resolution prediction. This is disclosed in the result panel when the matched grid cell is far from the address.
- **"Potential causes"**: real historical `FireCauseGeneral`/`FireCauseSpecific` values from your 2026 incident data, aggregated within ~140 miles of the queried location.
- **AI-generated report**: optional. The user pastes their own OpenAI API key into the page at view-time; it's sent directly from the browser to OpenAI and never touches this codebase. No key is stored anywhere in these files.

## Rebuilding the data

`build/` contains the Python scripts that turned your `PTA` folder's raw data
(MODIS text files, `2026_fire.csv`, `us_weather_2026_grid.csv`) into the
`data/*.json` files the site loads. They were written to run without
scikit-learn/geopandas (`mini_forest.py` is a from-scratch, numpy-only
random forest) since this build environment had no package-install access.
If you have scikit-learn available, re-training with the real
`RandomForestClassifier` from your notebook would likely improve fidelity;
swap it in and re-run `train_model.py` + `export_frontend_data.py`.

## Security note

Your notebook (`pta.ipynb`, cell 18) had a live OpenAI API key hardcoded in
plaintext. That key is not used anywhere in this site, but please revoke/rotate
it in your OpenAI dashboard if you haven't already.
