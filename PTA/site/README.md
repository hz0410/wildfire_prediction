# PTA Wildfire Risk Site

A static, scrollytelling wildfire site: national fire/acreage trends, big-fire
case studies, and an interactive U.S. address lookup backed by a random-forest
model trained on your 2026 PTA data.

## How to open it

The charts and prediction model are static, but Qwen report generation uses the
local Python service in `server/`. To run the complete application from the
repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r site/server/requirements.txt
uvicorn --app-dir site server.app:app --host 127.0.0.1 --port 8000
```

Then visit `http://127.0.0.1:8000`. The 28 GB Qwen checkpoint is loaded lazily
on the first report request. A CUDA GPU with roughly 30+ GB of available memory
is the simplest configuration for the bf16 checkpoint; multi-GPU placement is
handled by `device_map="auto"`. CPU execution is possible but generally too
slow for an interactive report. Set `QWEN_MODEL_PATH` if the checkpoint moves.

If reports are not needed, the site can still be served as a plain static site
(`index.html` + `css/` + `js/` + `data/`):

- **VS Code**: install the "Live Server" extension, right-click `index.html`, "Open with Live Server".
- **Terminal**: `cd` into this folder and run `python3 -m http.server 8000`, then visit `http://localhost:8000`.
- **Deploy**: push this folder to a GitHub repo and enable GitHub Pages (same setup as the reference template).

An internet connection is needed at view-time for the U.S. Census geocoder,
map tiles, CDN scripts, and (when a Qwen report is requested) Open-Meteo weather
and National Weather Service alerts. The server only calls those allow-listed,
read-only sources; Qwen itself is not given unrestricted network access.

## What's real vs. approximated

- **National fires-per-year / acres-per-year charts**: real NIFC statistics, 1983-2025.
- **Big fire case studies**: real, individually verified (Wikipedia/CAL FIRE/NPR/etc. -- sources linked on each card).
- **Address lookup, dates on or before 2026-06-26**: real observed 2026 MODIS satellite detections and reported fire-incident data (ground truth, not a prediction).
- **Address lookup, dates after 2026-06-26**: a random-forest model (60 trees, trained on this repo's real 2026 fire + weather panel; holdout ROC AUC ~0.82) predicts next-day fire probability and scale. Because there's no real future weather forecast in this dataset, future weather is estimated from a day-of-year seasonal fit rather than an actual forecast, and fire-history features assume no new fires occur between the data cutoff and the requested date. This is documented in the UI itself.
- **1km circle on the map**: shows the requested location; the underlying model resolution is a 1-degree (~111km) grid cell, so this is the "nearest modeled area," not a literal 1km-resolution prediction. This is disclosed in the result panel when the matched grid cell is far from the address.
- **"Potential causes"**: real historical `FireCauseGeneral`/`FireCauseSpecific` values from your 2026 incident data, aggregated within ~140 miles of the queried location.
- **AI-generated report**: optional. Local Qwen3-14B receives the random-forest
  output plus retrieved public weather/alert evidence and writes the report.
  The random forest remains the calibrated probability engine. Qwen must not
  invent or recalculate a probability, and its system prompt requires explicit
  uncertainty and source links.

## LoRA tuning Qwen

`tuning/train_lora.py` adds a parameter-efficient adapter without overwriting
the base checkpoint. `tuning/fire_reports.jsonl` is a schema/example only; one
example is not enough for a useful tune. Build a reviewed training/evaluation
set with diverse locations, risk bands, tool failures, past/future dates, and
answers that never invent evidence. Keep a location/time-disjoint test set.

```bash
python site/tuning/train_lora.py \
  --data site/tuning/fire_reports.jsonl \
  --output Models/Qwen3-14B-fire-lora

QWEN_ADAPTER_PATH=Models/Qwen3-14B-fire-lora \
  uvicorn --app-dir site server.app:app --host 127.0.0.1 --port 8000
```

Full-precision LoRA still has substantial memory requirements. For smaller
GPUs, adapt the script to QLoRA/4-bit loading after installing bitsandbytes.
Before deployment, evaluate report grounding separately from the random
forest's probability metrics; tuning prose does not improve AUC or calibration.

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
