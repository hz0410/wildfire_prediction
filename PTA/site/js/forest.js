// Client-side re-implementation of the PTA random-forest wildfire model.
// The trees themselves were trained in Python (see /site_build scripts) on
// real 2026 MODIS + incident + weather data, then exported as plain JSON so
// they can run directly in the browser -- no server, no API key needed for
// this part.

/** Walk one decision tree. `node` is {f, t, l, r} for splits or {p:[...]} for leaves. */
function forestTreePredict(node, features) {
  while (node.p === undefined) {
    const v = features[node.f];
    const goLeft = Number.isFinite(v) ? v <= node.t : true;
    node = goLeft ? node.l : node.r;
  }
  return node.p;
}

/** Average leaf probability vectors across every tree in the forest. */
function forestPredictProba(forestJson, features) {
  const nClasses = forestJson.classes.length;
  const acc = new Array(nClasses).fill(0);
  for (const tree of forestJson.trees) {
    const p = forestTreePredict(tree, features);
    for (let i = 0; i < nClasses; i++) acc[i] += p[i];
  }
  return acc.map((x) => x / forestJson.trees.length);
}

function forestPredictClass(forestJson, features) {
  const proba = forestPredictProba(forestJson, features);
  let bestIdx = 0;
  for (let i = 1; i < proba.length; i++) if (proba[i] > proba[bestIdx]) bestIdx = i;
  return { label: forestJson.classes[bestIdx], proba };
}

function dayOfYearUTC(date) {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.floor((date.getTime() - start) / 86400000) + 1;
}

/**
 * Build the exact feature vector the Python model expects, for an arbitrary
 * FUTURE 2026 date at a given grid cell. Because no ground truth exists past
 * the cutoff date, this assumes a "no further fire activity" baseline scenario
 * for the fire/case lag features (mirrors how the notebook's next-day model
 * would see a quiet run of days), and estimates weather from a day-of-year
 * seasonal fit (climatology) plus that cell's recent observed anomaly.
 */
function buildFutureFeatureVector(featureCols, cell, targetDateStr, cutoffDateStr, climatology, colMedians) {
  const targetDate = new Date(targetDateStr + 'T00:00:00Z');
  const cutoffDate = new Date(cutoffDateStr + 'T00:00:00Z');
  const daysAhead = Math.round((targetDate - cutoffDate) / 86400000);
  const doy = dayOfYearUTC(targetDate);
  const month = targetDate.getUTCMonth() + 1;
  const sinDoy = Math.sin((2 * Math.PI * doy) / 366);
  const cosDoy = Math.cos((2 * Math.PI * doy) / 366);

  function lagSum(series14, window) {
    let total = 0;
    for (let back = 1; back <= window; back++) {
      const offset = daysAhead - back; // 0 = cutoff day itself
      if (offset > 0) continue; // day is after cutoff -> no assumed activity
      const idx = 13 + offset;
      if (idx >= 0 && idx < 14) total += series14[idx];
    }
    return total;
  }

  const values = {
    lat_bin: cell.lat_bin,
    lon_bin: cell.lon_bin,
    month,
    dayofyear: doy,
    sin_doy: sinDoy,
    cos_doy: cosDoy,
    satellite_fire_count_lag_1d: lagSum(cell.fire_count_14, 1),
    total_frp_lag_1d: lagSum(cell.total_frp_14, 1),
    satellite_fire_count_lag_3d: lagSum(cell.fire_count_14, 3),
    total_frp_lag_3d: lagSum(cell.total_frp_14, 3),
    satellite_fire_count_lag_7d: lagSum(cell.fire_count_14, 7),
    total_frp_lag_7d: lagSum(cell.total_frp_14, 7),
    satellite_fire_count_lag_14d: lagSum(cell.fire_count_14, 14),
    total_frp_lag_14d: lagSum(cell.total_frp_14, 14),
    case_count_lag_1d: lagSum(cell.case_count_14, 1),
    total_case_acres_lag_1d: lagSum(cell.total_case_acres_14, 1),
    case_count_lag_3d: lagSum(cell.case_count_14, 3),
    total_case_acres_lag_3d: lagSum(cell.total_case_acres_14, 3),
    case_count_lag_7d: lagSum(cell.case_count_14, 7),
    total_case_acres_lag_7d: lagSum(cell.total_case_acres_14, 7),
    case_count_lag_14d: lagSum(cell.case_count_14, 14),
    total_case_acres_lag_14d: lagSum(cell.total_case_acres_14, 14),
    days_since_satellite_fire: Math.min(999, cell.days_since_satellite_fire_cutoff + Math.max(daysAhead, 0)),
    days_since_reported_case: Math.min(999, cell.days_since_reported_case_cutoff + Math.max(daysAhead, 0)),
  };

  for (const col in climatology) {
    const c = climatology[col];
    const climPred = c.a + c.b * Math.cos((2 * Math.PI * doy) / 366) + c.c * Math.sin((2 * Math.PI * doy) / 366);
    const anomaly = (cell.weather_anomaly && cell.weather_anomaly[col]) || 0;
    values[col] = climPred + anomaly;
  }

  return featureCols.map((name, i) => (values[name] !== undefined && Number.isFinite(values[name]) ? values[name] : colMedians[i]));
}
