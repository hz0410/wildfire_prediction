const DATA_DIR = 'data/';
const state = {};

async function loadJSON(name) {
  const res = await fetch(DATA_DIR + name);
  if (!res.ok) throw new Error('Failed to load ' + name);
  return res.json();
}

function fmtNum(n) {
  return Math.round(n).toLocaleString('en-US');
}
function fmtAcres(n) {
  return fmtNum(n) + ' acres';
}
function fmtUSD(n) {
  if (!n) return null;
  if (n >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(0) + 'M';
  return '$' + fmtNum(n);
}

// ---------------------------------------------------------------------------
// Section 1 + 2: national storyline charts
// ---------------------------------------------------------------------------
function renderStoryCharts(annual) {
  const years = annual.annual.map((d) => d.year);
  const fires = annual.annual.map((d) => d.fires);
  const acres = annual.annual.map((d) => d.acres);
  const humanPct = annual.annual.map((d) => d.human_caused_pct);

  const peakFireYear = annual.annual.reduce((a, b) => (b.fires > a.fires ? b : a));
  const peakAcreYear = annual.annual.reduce((a, b) => (b.acres > a.acres ? b : a));
  document.getElementById('fires-stat-callout').textContent =
    `Peak year: ${peakFireYear.year} with ${fmtNum(peakFireYear.fires)} fires. ` +
    `Most acres burned in a single year: ${peakAcreYear.year}, ${fmtAcres(peakAcreYear.acres)}.`;

  const humanValues = humanPct.filter((v) => v !== null && v !== undefined);
  const avgHuman = humanValues.reduce((a, b) => a + b, 0) / humanValues.length;
  document.getElementById('human-caused-avg').textContent = avgHuman.toFixed(0);

  new Chart(document.getElementById('chart-fires'), {
    type: 'bar',
    data: {
      labels: years,
      datasets: [{
        label: 'Wildfires reported',
        data: fires,
        backgroundColor: '#ff6b35',
        borderRadius: 2,
      }],
    },
    options: chartOptions('Fires per year (1983–2025)'),
  });

  new Chart(document.getElementById('chart-acres'), {
    type: 'bar',
    data: {
      labels: years,
      datasets: [{
        label: 'Acres burned',
        data: acres,
        backgroundColor: '#ffb703',
        borderRadius: 2,
      }],
    },
    options: chartOptions('Acres burned per year (1983–2025)'),
  });
}

function chartOptions(title) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: { display: true, text: title, color: '#f2ede6', font: { size: 13 } },
    },
    scales: {
      x: { ticks: { color: '#b9b3aa', maxTicksLimit: 12 }, grid: { color: '#262b2f' } },
      y: { ticks: { color: '#b9b3aa' }, grid: { color: '#262b2f' } },
    },
  };
}

// ---------------------------------------------------------------------------
// Section 3: big fire case studies
// ---------------------------------------------------------------------------
function renderCaseCards(cases) {
  const container = document.getElementById('case-cards');
  container.innerHTML = cases.map((c) => `
    <div class="case-card">
      <h3>${c.name}</h3>
      <div class="case-meta">${c.year} &middot; ${c.state}</div>
      <div class="case-stats">
        <div><b>${fmtAcres(c.acres)}</b>burned</div>
        <div><b>${c.deaths}</b>deaths</div>
        <div><b>${fmtNum(c.structures_destroyed)}</b>structures lost</div>
        ${c.cost_usd ? `<div><b>${fmtUSD(c.cost_usd)}</b>cost</div>` : ''}
      </div>
      <p class="blurb">${c.blurb}</p>
      <p class="case-meta">Cause: ${c.cause}</p>
      <a class="src" href="${c.source}" target="_blank" rel="noopener">source &rarr;</a>
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Section 4: interactive map
// ---------------------------------------------------------------------------
let leafletMap, marker, circle;

function initMap() {
  leafletMap = L.map('map').setView([39.8, -98.6], 4);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(leafletMap);
}

function setMapLocation(lat, lon) {
  if (marker) leafletMap.removeLayer(marker);
  if (circle) leafletMap.removeLayer(circle);
  marker = L.marker([lat, lon]).addTo(leafletMap);
  circle = L.circle([lat, lon], { radius: 1000, color: '#ff6b35', fillOpacity: 0.12 }).addTo(leafletMap);
  leafletMap.setView([lat, lon], 11);
}

async function geocodeAddress(address) {
  const url = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress' +
    '?address=' + encodeURIComponent(address) + '&benchmark=Public_AR_Current&format=json';
  const res = await fetch(url);
  if (!res.ok) throw new Error('Geocoder request failed');
  const json = await res.json();
  const matches = json.result && json.result.addressMatches;
  if (!matches || matches.length === 0) return null;
  const m = matches[0];
  return {
    lat: m.coordinates.y,
    lon: m.coordinates.x,
    matchedAddress: m.matchedAddress,
  };
}

function nearestCell(lat, lon) {
  let best = null;
  let bestDist = Infinity;
  const cosLat = Math.cos((lat * Math.PI) / 180);
  for (const cell of state.gridIndex) {
    const clat = cell.lat_bin + 0.5;
    const clon = cell.lon_bin + 0.5;
    const dlat = lat - clat;
    const dlon = (lon - clon) * cosLat;
    const dist = Math.sqrt(dlat * dlat + dlon * dlon);
    if (dist < bestDist) {
      bestDist = dist;
      best = cell;
    }
  }
  return { cell: best, distDeg: bestDist, distMiles: bestDist * 69 };
}

function riskBandFromProbability(p) {
  if (p < 0.2) return 'Low';
  if (p < 0.5) return 'Moderate';
  if (p < 0.75) return 'High';
  return 'Extreme';
}

function causeTips(causeNames) {
  const tips = {
    'Human': 'Most human-caused ignitions are preventable: check local burn-ban status before any outdoor burning, fully extinguish campfires (stir, soak, stir again), and avoid dragging trailer chains or mowing dry grass on hot/windy days.',
    'Natural': 'Lightning-caused starts can\'t be prevented, but dry-lightning risk is a signal to have a evacuation plan ready and to clear defensible space around structures in advance.',
    'Debris and Open Burning': 'Skip debris burning on dry or windy days; check for local burn permits and burn bans first.',
    'Equipment and Vehicle Use': 'Keep spark arrestors maintained on equipment/vehicles, avoid off-road driving or parking over dry grass, and carry a fire extinguisher.',
    'Recreation and Ceremony': 'Fully extinguish campfires and coals, and avoid fireworks or sky lanterns in dry vegetation.',
    'Arson': 'Report unattended or suspicious fires immediately to local authorities.',
    'Railroad Operations': 'Rail-adjacent dry vegetation is a known ignition point after brake/wheel sparking; local agencies sometimes clear vegetation buffers along rail corridors.',
    'Power Generation/Transmission/Distribution': 'In high-wind red-flag conditions, utilities may proactively shut off power (PSPS) in high-risk areas; sign up for utility wildfire-safety alerts if available in your area.',
    'Firearms and Explosives Use': 'Avoid target shooting with tracer/incendiary ammunition in dry vegetation.',
    'Fireworks': 'Avoid fireworks entirely in dry vegetation or during burn bans; many CA/AZ/CO/etc. counties ban all consumer fireworks during fire season.',
  };
  const out = [];
  for (const name of causeNames) {
    if (tips[name]) out.push(tips[name]);
  }
  if (out.length === 0) {
    out.push('Follow local fire restrictions, keep vegetation cleared 5-30 feet from structures, and have an evacuation plan ready during red-flag warning days.');
  }
  return out;
}

function renderCauses(gridId) {
  const causeData = state.cellCauses[gridId];
  if (!causeData) {
    return { html: '<p class="small-note">No nearby reported-cause history in our 2026 dataset for this area.</p>', causeNames: [] };
  }
  const generalEntries = Object.entries(causeData.general).sort((a, b) => b[1] - a[1]);
  const causeNames = generalEntries.map((e) => e[0]);
  const html = `
    <ul>${generalEntries.map(([name, n]) => `<li><b>${name}</b> &mdash; ${n} of ${causeData.n_nearby_cases} nearby reported fires in 2026</li>`).join('')}</ul>
    <p class="small-note">Based on ${causeData.n_nearby_cases} reported incidents within ~140 miles in the 2026 dataset.</p>
  `;
  return { html, causeNames };
}

async function handleLookup() {
  const address = document.getElementById('address-input').value.trim();
  const dateStr = document.getElementById('date-input').value;
  const statusEl = document.getElementById('lookup-status');
  const panel = document.getElementById('result-panel');
  if (!address) {
    statusEl.textContent = 'Enter a U.S. address first.';
    return;
  }
  statusEl.textContent = 'Locating address…';
  panel.innerHTML = '<p class="result-placeholder">Working on it…</p>';

  let geo = null;
  const latLonMatch = address.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (latLonMatch) {
    geo = { lat: parseFloat(latLonMatch[1]), lon: parseFloat(latLonMatch[2]), matchedAddress: address };
  } else {
    try {
      geo = await geocodeAddress(address);
    } catch (e) {
      statusEl.textContent = 'Could not reach the geocoding service (US Census geocoder). If this persists, try entering coordinates directly as "lat, lon".';
      return;
    }
  }
  if (!geo) {
    statusEl.textContent = 'No match found for that address. Try adding city and state, or enter coordinates as "lat, lon".';
    return;
  }
  statusEl.textContent = `Matched: ${geo.matchedAddress}`;
  setMapLocation(geo.lat, geo.lon);

  const { cell, distMiles } = nearestCell(geo.lat, geo.lon);
  const cutoff = state.featureMeta.cutoff_date;
  const isPast = dateStr <= cutoff;
  const farAway = distMiles > 190;

  let bodyHtml = '';
  const causes = renderCauses(cell.grid_id);

  if (farAway) {
    bodyHtml += `<p class="small-note">The nearest modeled grid cell with any 2026 fire signal is ~${Math.round(distMiles)} miles away, so this is a regional approximation, not a precise local read.</p>`;
  }

  if (isPast) {
    const events = state.dailyEvents[cell.grid_id] || {};
    const dayEvent = events[dateStr];
    let level = 'None';
    let detailHtml = '';
    if (dayEvent) {
      level = dayEvent.reported_fire_level && dayEvent.reported_fire_level !== 'None'
        ? dayEvent.reported_fire_level
        : (dayEvent.fire_count > 0 ? 'Moderate' : 'None');
      detailHtml = `
        <ul>
          <li>Satellite (MODIS) detections that day: <b>${dayEvent.fire_count}</b>${dayEvent.total_frp ? `, total fire radiative power ${dayEvent.total_frp}` : ''}</li>
          <li>Reported fire cases that day: <b>${dayEvent.case_count}</b>${dayEvent.max_case_acres ? `, largest ${fmtAcres(dayEvent.max_case_acres)}` : ''}</li>
        </ul>`;
    } else {
      // look for nearby days with activity for context
      const nearby = Object.keys(events).filter((d) => Math.abs(dateOffset(d, dateStr)) <= 14).sort();
      if (nearby.length) {
        detailHtml = `<p class="small-note">No recorded activity on this exact date. Nearby recorded activity: ${nearby.slice(0, 5).join(', ')}.</p>`;
      } else {
        detailHtml = '<p class="small-note">No satellite detections or reported fire cases recorded at this location in our 2026 dataset.</p>';
      }
    }
    bodyHtml += `
      <p class="source-tag">Observed data (ground truth), not a model prediction</p>
      <span class="risk-badge risk-${level}">${level} activity</span>
      ${detailHtml}
    `;
  } else {
    const cellState = state.cellState[cell.grid_id];
    const featureVec = buildFutureFeatureVector(
      state.featureMeta.feature_cols, cellState, dateStr, cutoff,
      state.climatology, state.featureMeta.col_medians
    );
    const riskIdx = state.forestRisk.classes.indexOf('1.0');
    const proba = forestPredictProba(state.forestRisk, featureVec)[riskIdx];
    const band = riskBandFromProbability(proba);
    const levelPred = forestPredictClass(state.forestLevel, featureVec).label;
    bodyHtml += `
      <p class="source-tag">Random-forest model prediction (trained on 2026 data, holdout ROC AUC ${state.featureMeta.holdout_auc.toFixed(2)})</p>
      <span class="risk-badge risk-${band}">${band} risk &middot; ${(proba * 100).toFixed(1)}%</span>
      <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${Math.min(100, proba * 100)}%"></div></div>
      <ul>
        <li>Modeled probability of a reported fire case the following day: <b>${(proba * 100).toFixed(1)}%</b></li>
        <li>Predicted fire scale if one occurs: <b>${levelPred}</b></li>
      </ul>
      <p class="small-note">Future-date estimate assumes no new fire activity between the data cutoff (${cutoff}) and this date, and uses a seasonal weather estimate rather than a real forecast.</p>
    `;
  }

  bodyHtml += `<h4>Potential causes</h4>${causes.html}`;
  const tips = causeTips(causes.causeNames);
  bodyHtml += `<h4>Prevention steps</h4><ul>${tips.map((t) => `<li>${t}</li>`).join('')}</ul>`;
  bodyHtml += renderLLMBox();

  panel.innerHTML = `<h3>${geo.matchedAddress}</h3>` + bodyHtml;
  wireLLMBox({ address: geo.matchedAddress, dateStr, isPast, cell, causes });
}

function dateOffset(a, b) {
  return (new Date(a) - new Date(b)) / 86400000;
}

// ---------------------------------------------------------------------------
// Optional "bring your own OpenAI key" LLM report
// ---------------------------------------------------------------------------
function renderLLMBox() {
  return `
    <div class="llm-box">
      <h4 style="margin-top:0">Generate a plain-English report (optional)</h4>
      <p class="small-note">Paste your own OpenAI API key to have a short natural-language report written from the numbers above. Your key is sent directly from your browser to OpenAI and is never saved or sent anywhere else. Leave blank to just read the template below.</p>
      <input type="password" id="openai-key" placeholder="sk-..." autocomplete="off" />
      <button id="generate-report-btn">Generate report</button>
      <div id="llm-report" class="llm-report"></div>
    </div>
  `;
}

function templateReport(ctx) {
  return `Template report (no API key used):\n\n` +
    `Location: ${ctx.address}\nDate: ${ctx.dateStr}\n\n` +
    `${ctx.isPast ? 'Based on recorded 2026 data' : 'Based on the random-forest model'} for the nearest modeled grid cell, ` +
    `see the risk badge and cause list above. To prevent human-caused ignition: avoid open burning on dry/windy days, ` +
    `fully extinguish campfires and coals, keep equipment spark arrestors maintained, and follow any local burn bans or fire restrictions.`;
}

function wireLLMBox(ctx) {
  const btn = document.getElementById('generate-report-btn');
  const out = document.getElementById('llm-report');
  out.textContent = templateReport(ctx);
  btn.addEventListener('click', async () => {
    const key = document.getElementById('openai-key').value.trim();
    if (!key) {
      out.textContent = templateReport(ctx);
      return;
    }
    out.textContent = 'Generating…';
    try {
      const prompt = `You are a wildfire risk assistant for local communities. Using ONLY the context below ` +
        `(no outside knowledge of current events), write a concise (under 100 words) plain-English report covering: ` +
        `likelihood of fire, expected scale/severity if relevant, likely causes, and concrete human-caused-ignition prevention steps.\n\n` +
        `Location: ${ctx.address}\nDate: ${ctx.dateStr}\nData type: ${ctx.isPast ? 'observed 2026 record' : 'random-forest model prediction'}\n` +
        `Nearby historical causes: ${ctx.causes.causeNames.join(', ') || 'unknown'}`;
      const res = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + key,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: prompt }],
          max_tokens: 220,
        }),
      });
      const json = await res.json();
      if (json.error) throw new Error(json.error.message);
      out.textContent = json.choices[0].message.content.trim();
    } catch (e) {
      out.textContent = 'Could not reach OpenAI (' + e.message + '). Showing template instead:\n\n' + templateReport(ctx);
    }
  });
}

// ---------------------------------------------------------------------------
// Section 5: SHAP-style feature attribution
// ---------------------------------------------------------------------------
const FEATURE_META = {
  lat_bin: { icon: '📍', label: 'Latitude', desc: 'North-south location of the grid cell.' },
  lon_bin: { icon: '📍', label: 'Longitude', desc: 'East-west location of the grid cell.' },
  month: { icon: '📅', label: 'Month', desc: 'Calendar month, a coarse seasonality signal.' },
  dayofyear: { icon: '📅', label: 'Day of year', desc: 'Day number 1-366, feeds the seasonal cycle.' },
  sin_doy: { icon: '🔄', label: 'Season (sin)', desc: 'Cyclical encoding of time of year.' },
  cos_doy: { icon: '🔄', label: 'Season (cos)', desc: 'Cyclical encoding of time of year.' },
  satellite_fire_count_lag_1d: { icon: '🛰️', label: 'Satellite detections, last 1 day', desc: 'MODIS fire detections the day before.' },
  satellite_fire_count_lag_3d: { icon: '🛰️', label: 'Satellite detections, last 3 days', desc: 'MODIS fire detections in the last 3 days.' },
  satellite_fire_count_lag_7d: { icon: '🛰️', label: 'Satellite detections, last 7 days', desc: 'MODIS fire detections in the last week.' },
  satellite_fire_count_lag_14d: { icon: '🛰️', label: 'Satellite detections, last 14 days', desc: 'MODIS fire detections in the last two weeks.' },
  total_frp_lag_1d: { icon: '🔥', label: 'Fire radiative power, last 1 day', desc: 'Satellite-estimated fire intensity, last day.' },
  total_frp_lag_3d: { icon: '🔥', label: 'Fire radiative power, last 3 days', desc: 'Satellite-estimated fire intensity, last 3 days.' },
  total_frp_lag_7d: { icon: '🔥', label: 'Fire radiative power, last 7 days', desc: 'Satellite-estimated fire intensity, last week.' },
  total_frp_lag_14d: { icon: '🔥', label: 'Fire radiative power, last 14 days', desc: 'Satellite-estimated fire intensity, last two weeks.' },
  case_count_lag_1d: { icon: '🚒', label: 'Reported fires nearby, last 1 day', desc: 'Officially reported incidents, last day.' },
  case_count_lag_3d: { icon: '🚒', label: 'Reported fires nearby, last 3 days', desc: 'Officially reported incidents, last 3 days.' },
  case_count_lag_7d: { icon: '🚒', label: 'Reported fires nearby, last 7 days', desc: 'Officially reported incidents, last week.' },
  case_count_lag_14d: { icon: '🚒', label: 'Reported fires nearby, last 14 days', desc: 'Officially reported incidents, last two weeks.' },
  total_case_acres_lag_1d: { icon: '🌲', label: 'Acres burned nearby, last 1 day', desc: 'Reported acreage, last day.' },
  total_case_acres_lag_3d: { icon: '🌲', label: 'Acres burned nearby, last 3 days', desc: 'Reported acreage, last 3 days.' },
  total_case_acres_lag_7d: { icon: '🌲', label: 'Acres burned nearby, last 7 days', desc: 'Reported acreage, last week.' },
  total_case_acres_lag_14d: { icon: '🌲', label: 'Acres burned nearby, last 14 days', desc: 'Reported acreage, last two weeks.' },
  days_since_satellite_fire: { icon: '⏱️', label: 'Days since last satellite fire', desc: 'How long since MODIS last saw fire here.' },
  days_since_reported_case: { icon: '⏱️', label: 'Days since last reported fire', desc: 'How long since an incident was last reported here.' },
  temperature_2m_max: { icon: '🌡️', label: 'Max temperature', desc: 'Daily maximum air temperature.' },
  temperature_2m_min: { icon: '🌡️', label: 'Min temperature', desc: 'Daily minimum air temperature.' },
  temperature_2m_mean: { icon: '🌡️', label: 'Mean temperature', desc: 'Daily average air temperature.' },
  temperature_2m_range: { icon: '🌡️', label: 'Temperature range', desc: 'Daily high minus low, a dryness signal.' },
  precipitation_sum: { icon: '🌧️', label: 'Rainfall', desc: 'Total daily precipitation.' },
  wind_speed_10m_max: { icon: '💨', label: 'Max wind speed', desc: 'Daily peak wind speed, drives fire spread.' },
  sunshine_duration: { icon: '☀️', label: 'Sunshine duration', desc: 'Seconds of direct sunshine that day.' },
  sunshine_hours: { icon: '☀️', label: 'Sunshine hours', desc: 'Hours of direct sunshine that day.' },
};

function featureMetaFor(name) {
  return FEATURE_META[name] || { icon: '📊', label: name, desc: 'Model input feature.' };
}

function renderShapSection(shap) {
  const top = shap.summary.slice(0, 8);
  const cardsHtml = top.map((f) => {
    const meta = featureMetaFor(f.feature);
    const up = f.mean_signed_shap >= 0;
    return `
      <div class="variable-explainer-card">
        <span class="ve-icon">${meta.icon}</span>
        <strong>${meta.label}</strong>
        <p>${meta.desc}</p>
        <span class="ve-shap-tag ${up ? 'up' : 'down'}">${up ? '↑ raises risk' : '↓ lowers risk'} on average</span>
      </div>`;
  }).join('');
  document.getElementById('shap-cards').innerHTML = cardsHtml;

  const top15 = shap.summary.slice(0, 15);
  new Chart(document.getElementById('chart-shap'), {
    type: 'bar',
    data: {
      labels: top15.map((f) => featureMetaFor(f.feature).label),
      datasets: [{
        label: 'Mean |SHAP value|',
        data: top15.map((f) => f.mean_abs_shap),
        backgroundColor: top15.map((f) => (f.mean_signed_shap >= 0 ? '#c0392b' : '#2f9e6e')),
        borderRadius: 3,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Mean |SHAP| = ${ctx.raw.toFixed(4)} probability points`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#4b5563' }, grid: { color: '#eee' }, title: { display: true, text: 'Mean |SHAP value| (probability points)', color: '#4b5563' } },
        y: { ticks: { color: '#1f2937' }, grid: { display: false } },
      },
    },
  });

  document.getElementById('shap-note').innerHTML =
    `Computed with a Shapley-sampling estimator (${shap.method}) over ${shap.n_instances_explained} held-out ` +
    `days, explaining the risk model's predicted probability. Base rate (average predicted risk across the ` +
    `background sample): ${(shap.base_value * 100).toFixed(1)}%. ` +
    `The dominant drivers are recent nearby fire history (how long since the last reported fire, and how many ` +
    `fires/acres in the last 1-14 days) &mdash; weather and location matter, but recent activity dominates.`;
}

// ---------------------------------------------------------------------------
// Section 6: model performance
// ---------------------------------------------------------------------------
function renderPerformanceSection(perf) {
  const kpis = [
    { title: 'ROC AUC', value: perf.roc_auc.toFixed(3), note: 'risk model, held-out days' },
    { title: 'Precision @ 0.35', value: (perf.precision * 100).toFixed(1) + '%', note: 'of flagged days, how many were real' },
    { title: 'Recall @ 0.35', value: (perf.recall * 100).toFixed(1) + '%', note: 'of real fire-days, how many were flagged' },
    { title: 'F1 @ 0.35', value: perf.f1.toFixed(3), note: 'precision/recall balance' },
    { title: 'Accuracy @ 0.35', value: (perf.accuracy * 100).toFixed(1) + '%', note: 'can be misleading -- see note below' },
    { title: 'Fire-scale accuracy', value: (perf.level_model.accuracy * 100).toFixed(1) + '%', note: '5-class scale model' },
  ];
  document.getElementById('kpi-cards').innerHTML = kpis.map((k) => `
    <div class="kpi-card">
      <div class="kpi-title">${k.title}</div>
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-note">${k.note}</div>
    </div>`).join('');

  new Chart(document.getElementById('chart-roc'), {
    type: 'line',
    data: {
      labels: perf.roc_curve.fpr.map((x) => x.toFixed(2)),
      datasets: [
        {
          label: 'Model',
          data: perf.roc_curve.fpr.map((x, i) => ({ x, y: perf.roc_curve.tpr[i] })),
          borderColor: '#c0392b',
          backgroundColor: 'rgba(192,57,43,0.08)',
          fill: true,
          tension: 0.15,
          pointRadius: 0,
        },
        {
          label: 'Random baseline',
          data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
          borderColor: '#94a3b8',
          borderDash: [6, 4],
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      plugins: { legend: { labels: { color: '#4b5563' } } },
      scales: {
        x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'False positive rate', color: '#4b5563' }, ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
        y: { min: 0, max: 1, title: { display: true, text: 'True positive rate', color: '#4b5563' }, ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
      },
    },
  });

  new Chart(document.getElementById('chart-calibration'), {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Observed rate',
          data: perf.calibration.map((c) => ({ x: c.predicted_mean, y: c.observed_rate })),
          borderColor: '#c0392b',
          backgroundColor: '#c0392b',
          showLine: true,
          tension: 0.1,
        },
        {
          label: 'Perfect calibration',
          data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
          borderColor: '#94a3b8',
          borderDash: [6, 4],
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      plugins: { legend: { labels: { color: '#4b5563' } } },
      scales: {
        x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'Mean predicted probability (bin)', color: '#4b5563' }, ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
        y: { min: 0, max: 1, title: { display: true, text: 'Observed fire rate (bin)', color: '#4b5563' }, ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
      },
    },
  });

  const cm = perf.confusion_matrix;
  document.getElementById('confusion-table').innerHTML = `
    <tr><th></th><th>Predicted: fire</th><th>Predicted: no fire</th></tr>
    <tr><th>Actual: fire</th><td class="hit">${cm.tp}</td><td class="miss">${cm.fn}</td></tr>
    <tr><th>Actual: no fire</th><td class="miss">${cm.fp}</td><td class="hit">${cm.tn}</td></tr>
  `;

  document.getElementById('level-table').innerHTML = `
    <tr><th>Scale</th><th>Support</th><th>Precision</th><th>Recall</th></tr>
    ${perf.level_model.per_class.map((c) => `<tr><td>${c.class}</td><td>${c.support}</td><td>${(c.precision * 100).toFixed(0)}%</td><td>${(c.recall * 100).toFixed(0)}%</td></tr>`).join('')}
  `;

  document.getElementById('performance-takeaway').innerHTML = `
    <h4>How to read this</h4>
    <ul>
      <li>Reported fires are rare: only <strong>${(perf.test_positive_rate * 100).toFixed(1)}%</strong> of held-out grid-days actually had one reported the next day. With that imbalance, <strong>accuracy is misleading</strong> &mdash; a model that always predicts "no fire" would already score ~${(100 - perf.test_positive_rate * 100).toFixed(1)}% accuracy while missing every real fire.</li>
      <li>We use a low decision threshold (0.35, matching the original notebook) because <strong>missing a real fire risk (a false negative) is far more costly than a false alarm</strong>. That's why recall (${(perf.recall * 100).toFixed(0)}%) is tuned high at the cost of precision (${(perf.precision * 100).toFixed(0)}%) &mdash; most flagged days turn out calm, but very few real fire-days slip through.</li>
      <li>ROC AUC of <strong>${perf.roc_auc.toFixed(2)}</strong> means the model ranks a random fire-day above a random non-fire-day about ${(perf.roc_auc * 100).toFixed(0)}% of the time &mdash; a meaningfully-better-than-chance signal, not a guarantee for any single address.</li>
      <li>The fire-<em>scale</em> model (None/Low/Moderate/High/Extreme) is much more accurate on the dominant "None" class than on rarer large-fire classes (see the table) &mdash; there are simply far fewer big-fire examples to learn from in one season of data.</li>
      <li>Trained on ${perf.n_train_rows.toLocaleString()} grid-days, evaluated on ${perf.n_test_rows.toLocaleString()} held-out grid-days from later in the season (a true time-based split), with ${perf.n_trees} trees and ${perf.n_features} input features.</li>
    </ul>
  `;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function main() {
  const [annual, bigFires, gridIndex, cellState, cellCauses, dailyEvents,
    forestRisk, forestLevel, featureMeta, climatology, shapAnalysis, modelPerformance] = await Promise.all([
    loadJSON('annual_stats.json'),
    loadJSON('big_fires.json'),
    loadJSON('grid_index.json'),
    loadJSON('cell_state.json'),
    loadJSON('cell_causes.json'),
    loadJSON('daily_events.json'),
    loadJSON('forest_risk.json'),
    loadJSON('forest_level.json'),
    loadJSON('feature_meta.json'),
    loadJSON('climatology.json'),
    loadJSON('shap_analysis.json'),
    loadJSON('model_performance.json'),
  ]);
  Object.assign(state, {
    gridIndex, cellState, cellCauses, dailyEvents, forestRisk, forestLevel, featureMeta, climatology,
  });

  renderStoryCharts(annual);
  renderCaseCards(bigFires);
  document.getElementById('cutoff-date-label').textContent = featureMeta.cutoff_date;
  initMap();
  renderShapSection(shapAnalysis);
  renderPerformanceSection(modelPerformance);

  document.getElementById('lookup-btn').addEventListener('click', handleLookup);
  document.getElementById('address-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleLookup();
  });
}

main().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML('afterbegin',
    `<div style="background:#e63946;color:#fff;padding:1rem;text-align:center">Failed to load site data: ${e.message}</div>`);
});
