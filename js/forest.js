// Client-side re-implementation of the site-demo wildfire risk model (v2).
// Trained in Python (build/train_model_v2.py) on a dense CONUS 0.25-degree
// grid using real 2026 FIRMS satellite fire history, real human-activity
// features (population, roads, fire-station distance), and a 2026 weather
// proxy, with the same "new ignition after 3+ quiet days" target definition
// as the real project model. Exported as plain JSON so it runs directly in
// the browser -- no server, no API key. This is the SITE-DEMO surrogate; the
// site's "Model Analysis" section documents the REAL project model's results
// separately (those come from precomputed artifacts, not this JS model).

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

function dayOfYearUTC(date) {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.floor((date.getTime() - start) / 86400000) + 1;
}

/**
 * Build the exact feature vector the v2 Python model expects, for an
 * arbitrary FUTURE date at a given dense grid cell. Past the data cutoff, we
 * assume a "no new observed activity" baseline for the fire-history lag
 * features (a quiet-days scenario), and estimate weather from a day-of-year
 * seasonal climatology fit plus that cell's recent observed anomaly.
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
    lat: cell.lat_bin + 0.125,
    lon: cell.lon_bin + 0.125,
    month,
    dayofyear: doy,
    sin_doy: sinDoy,
    cos_doy: cosDoy,
    fire_count_lag_1d: lagSum(cell.fire_count_14, 1),
    frp_lag_1d: lagSum(cell.total_frp_14, 1),
    fire_count_lag_3d: lagSum(cell.fire_count_14, 3),
    frp_lag_3d: lagSum(cell.total_frp_14, 3),
    fire_count_lag_7d: lagSum(cell.fire_count_14, 7),
    frp_lag_7d: lagSum(cell.total_frp_14, 7),
    fire_count_lag_14d: lagSum(cell.fire_count_14, 14),
    frp_lag_14d: lagSum(cell.total_frp_14, 14),
    days_since_satellite_fire: Math.min(999, cell.days_since_satellite_fire_cutoff + Math.max(daysAhead, 0)),
    population_per_sq_km: cell.population_per_sq_km,
    primary_road_km_per_100_sq_km: cell.primary_road_km_per_100_sq_km,
    log_population_density: cell.log_population_density,
    distance_to_fire_station_km: cell.distance_to_fire_station_km,
  };

  for (const col in climatology) {
    const c = climatology[col];
    const climPred = c.a + c.b * Math.cos((2 * Math.PI * doy) / 366) + c.c * Math.sin((2 * Math.PI * doy) / 366);
    const anomaly = (cell.weather_anomaly && cell.weather_anomaly[col]) || 0;
    values[col] = climPred + anomaly;
  }

  return featureCols.map((name, i) => (values[name] !== undefined && Number.isFinite(values[name]) ? values[name] : colMedians[i]));
}

/**
 * The forest is trained with "balanced_subsample"-style bootstrapping: every
 * tree draws an equal number of positive and negative rows (a 50/50 prior),
 * regardless of the real class balance. That makes raw predict_proba output
 * a probability *under the artificial balanced prior*, not the true
 * unconditional probability -- so it can't be compared directly against
 * calibrated real-world risk bands. This applies the standard prior
 * correction (Bayes' rule rescaling from the training prior back to the true
 * prior, the same idea used in case-control / rare-events logistic
 * regression correction) to rescale it back down to a realistic probability
 * before we bucket it into the real model's risk bands.
 */
function calibrateBalancedProba(pRaw, truePrior, trainPrior) {
  const w1 = truePrior / trainPrior;
  const w0 = (1 - truePrior) / (1 - trainPrior);
  const num = pRaw * w1;
  const den = num + (1 - pRaw) * w0;
  return den > 0 ? num / den : pRaw;
}

/** Map a site-demo probability onto the REAL model's risk bands (from the
 * project's model card), so the live map uses the same discrete, honestly-
 * calibrated language as the Model Analysis section, rather than an
 * arbitrary 0-1 scale. */
function riskBandFromProbability(p, bands) {
  if (p <= bands.typical_upper) return { label: 'Typical', id: 0 };
  if (p <= bands.moderate_upper) return { label: 'Moderate', id: 1 };
  if (p <= bands.elevated_upper) return { label: 'Elevated', id: 2 };
  if (p <= bands.high_upper) return { label: 'High', id: 3 };
  return { label: 'Extreme', id: 4 };
}
