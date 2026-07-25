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
function fmtPct(x, digits) {
  return (x * 100).toFixed(digits === undefined ? 1 : digits) + '%';
}

function chartOptions(title) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: { display: true, text: title, color: '#1f2937', font: { size: 13 } },
    },
    scales: {
      x: { ticks: { color: '#4b5563', maxTicksLimit: 12 }, grid: { color: '#eee' } },
      y: { ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
    },
  };
}

// ---------------------------------------------------------------------------
// Section 0: the cost of fire (real economic-loss data, 2020-2026)
// ---------------------------------------------------------------------------
function fmtUSDmillions(m) {
  if (m >= 1000) return '$' + (m / 1000).toFixed(m >= 10000 ? 0 : 1) + 'B';
  return '$' + fmtNum(m) + 'M';
}

function renderLossSection(lossData, annual) {
  const rows = lossData.annual;
  const pointValue = (r) => {
    if (r.cost_cpi_adjusted !== undefined) return r.cost_cpi_adjusted;
    if (r.cost_high !== null && r.cost_high !== undefined) return (r.cost_low + r.cost_high) / 2;
    return r.cost_low;
  };
  const colorFor = (r) => (
    r.estimate_type === 'official_noaa' ? '#c0392b'
      : r.estimate_type === 'third_party_estimate' ? '#7a1a12'
      : '#94a3b8'
  );

  new Chart(document.getElementById('chart-loss'), {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.year),
      datasets: [{
        label: 'Estimated wildfire cost ($M)',
        data: rows.map(pointValue),
        backgroundColor: rows.map(colorFor),
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const r = rows[ctx.dataIndex];
              const range = (r.cost_high !== null && r.cost_high !== undefined && r.cost_high !== r.cost_low)
                ? ` (range ${fmtUSDmillions(r.cost_low)}–${fmtUSDmillions(r.cost_high)})` : '';
              return [`${fmtUSDmillions(pointValue(r))}${range}`, r.event_name, r.estimate_type.replace(/_/g, ' ')];
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: '#4b5563' }, grid: { color: '#eee' } },
        y: {
          type: 'logarithmic',
          ticks: { color: '#4b5563', callback: (v) => fmtUSDmillions(v) },
          grid: { color: '#eee' },
          title: { display: true, text: 'Estimated cost (log scale)', color: '#4b5563' },
        },
      },
    },
  });

  // acres burned vs. dollar loss, for years present in both real datasets (2020-2025;
  // 2026 is a partial year and excluded here since full-year acreage isn't final yet)
  const acresByYear = {};
  annual.annual.forEach((a) => { acresByYear[a.year] = a.acres; });
  const overlapRows = rows.filter((r) => acresByYear[r.year] !== undefined);

  new Chart(document.getElementById('chart-loss-vs-acres'), {
    data: {
      labels: overlapRows.map((r) => r.year),
      datasets: [
        {
          type: 'bar',
          label: 'Acres burned',
          data: overlapRows.map((r) => acresByYear[r.year]),
          backgroundColor: 'rgba(224,168,0,0.28)',
          borderColor: 'rgba(224,168,0,0.9)',
          borderWidth: 1,
          yAxisID: 'yAcres',
          borderRadius: 3,
          order: 2,
        },
        {
          type: 'line',
          label: 'Estimated dollar loss',
          data: overlapRows.map(pointValue),
          borderColor: '#c0392b',
          backgroundColor: '#c0392b',
          pointBackgroundColor: '#c0392b',
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointRadius: 6,
          pointHoverRadius: 8,
          borderWidth: 3,
          yAxisID: 'yCost',
          tension: 0.2,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#4b5563' } } },
      elements: { line: { fill: false } },
      scales: {
        x: { ticks: { color: '#4b5563' }, grid: { display: false } },
        yAcres: {
          position: 'left',
          ticks: { color: '#4b5563', callback: (v) => (v / 1e6).toFixed(0) + 'M' },
          title: { display: true, text: 'Acres burned', color: '#4b5563' },
          grid: { color: '#eee' },
        },
        yCost: {
          position: 'right',
          type: 'logarithmic',
          ticks: { color: '#4b5563', callback: (v) => fmtUSDmillions(v) },
          title: { display: true, text: 'Estimated cost (log scale)', color: '#4b5563' },
          grid: { display: false },
        },
      },
    },
  });

  const y2020_24 = rows.filter((r) => r.estimate_type === 'official_noaa');
  const total2020_24 = y2020_24.reduce((s, r) => s + r.cost_cpi_adjusted, 0);
  const y2025 = rows.find((r) => r.year === 2025);
  const y2024 = rows.find((r) => r.year === 2024);
  const acres2024 = acresByYear[2024];

  document.getElementById('loss-analysis').innerHTML = `
    <h4>How to read this</h4>
    <ul>
      <li>From 2020 through 2024, NOAA's official disaster-cost tracker put the total cost of the single costliest qualifying U.S. wildfire event each year at <strong>${fmtUSDmillions(total2020_24)} combined</strong> across all five years &mdash; and then <strong>January 2025 alone</strong> (the Palisades and Eaton fires in Los Angeles) is estimated at <strong>${fmtUSDmillions(y2025.cost_low)}&ndash;${fmtUSDmillions(y2025.cost_high)}</strong>, by far the costliest wildfire event on record, larger than the previous five years combined even at the low end of the range.</li>
      <li>Dollar loss and acres burned genuinely diverge: ${y2024.year} burned about <strong>${(acres2024 / 1e6).toFixed(1)} million acres</strong> nationally (the most since 2020) but NOAA only tallied a single qualifying billion-dollar wildfire event that year, worth <strong>${fmtUSDmillions(y2024.cost_cpi_adjusted)}</strong> &mdash; because most of that acreage burned in lower-value rural and rangeland, not populated areas. The 2025 Los Angeles fires burned a tiny fraction of the acreage of a typical bad wildfire year, yet caused vastly more damage, because they hit dense urban-wildland interface.</li>
      <li>Estimates for the same event can vary by an order of magnitude depending on what's counted: insured-loss-only figures for the 2025 LA fires run $28&ndash;40B, while broader total-damage-and-economic-loss estimates (property, business interruption, indirect costs) reach $250&ndash;275B. Always check what a wildfire "cost" figure is actually measuring before comparing it to another one.</li>
      <li>NOAA discontinued ongoing updates to its Billion-Dollar Disasters tracker after the 2024 edition, so 2025 and 2026 rely on third-party or state-level estimates rather than one consistent government methodology &mdash; a real gap in the public data available for a project like this one.</li>
      <li>2026 is a partial year (through late July): nationally 130% of the 10-year average number of fires and 146% of the 10-year average acres burned so far, but no single event has crossed the billion-dollar threshold yet and peak fire season (August&ndash;October) hasn't happened. The suppression-cost figures shown here are a floor, not a final total.</li>
    </ul>
  `;
}

// ---------------------------------------------------------------------------
// Section 1 + 2: national storyline charts
// ---------------------------------------------------------------------------
function renderStoryCharts(annual) {
  const peakFireYear = annual.annual.reduce((a, b) => (b.fires > a.fires ? b : a));
  const peakAcreYear = annual.annual.reduce((a, b) => (b.acres > a.acres ? b : a));
  document.getElementById('fires-stat-callout').textContent =
    `Peak year: ${peakFireYear.year} with ${fmtNum(peakFireYear.fires)} fires. ` +
    `Most acres burned in a single year: ${peakAcreYear.year}, ${fmtAcres(peakAcreYear.acres)}.`;
}

// ---------------------------------------------------------------------------
// Section 1 (map): fires reported per state, by year (choropleth)
//
// Uses Plotly's built-in USA-states choropleth trace, which has state
// boundary geometry built into the plotly.js library itself -- no separate
// map-outline file needs to be fetched from a CDN at runtime, which is more
// robust than loading external topojson/geojson over the network.
// ---------------------------------------------------------------------------
const STATE_NAME_TO_ABBR = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA',
  Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', Florida: 'FL', Georgia: 'GA',
  Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA',
  Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD',
  Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS', Missouri: 'MO',
  Montana: 'MT', Nebraska: 'NE', Nevada: 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
  'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH',
  Oklahoma: 'OK', Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
  'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT',
  Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY',
};

function renderStateMap(firesByState) {
  const years = firesByState.years;
  const metricLabels = {
    reported_fires_nifc: 'wildfires reported (NIFC)',
    satellite_detections_firms: 'satellite fire detections (FIRMS, partial year)',
  };
  const stateNames = Object.keys(firesByState.states);

  // fixed color domain across all years, so shading is comparable when you
  // switch years rather than auto-rescaling each time
  let globalMax = 0;
  years.forEach((y) => {
    stateNames.forEach((name) => {
      globalMax = Math.max(globalMax, firesByState.states[name][String(y)] || 0);
    });
  });

  const plotDiv = document.getElementById('state-map');
  let selectedYear = 2025;

  function traceFor(year) {
    const metric = firesByState.metric_by_year[String(year)];
    const label = metric === 'satellite_detections_firms' ? 'satellite detections' : 'fires reported';
    return [{
      type: 'choropleth',
      locationmode: 'USA-states',
      locations: stateNames.map((name) => STATE_NAME_TO_ABBR[name]),
      z: stateNames.map((name) => firesByState.states[name][String(year)] || 0),
      text: stateNames.map((name) => `${name}: ${fmtNum(firesByState.states[name][String(year)] || 0)} ${label}`),
      hoverinfo: 'text',
      zmin: 0,
      zmax: globalMax,
      colorscale: [[0, '#fdf0ec'], [0.15, '#f5b8a3'], [0.4, '#e37a5c'], [0.7, '#c0392b'], [1, '#6e1c12']],
      marker: { line: { color: '#fff', width: 0.6 } },
      colorbar: { title: { text: label, side: 'right' }, thickness: 14, len: 0.75 },
    }];
  }

  const layout = {
    geo: {
      scope: 'usa',
      showlakes: true,
      lakecolor: '#eef2f5',
      bgcolor: 'rgba(0,0,0,0)',
    },
    margin: { l: 0, r: 0, t: 10, b: 0 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    height: 480,
    font: { family: '-apple-system, Helvetica, Arial, sans-serif', color: '#4b5563' },
  };

  Plotly.newPlot(plotDiv, traceFor(selectedYear), layout, { responsive: true, displayModeBar: false });

  function paint(year) {
    Plotly.react(plotDiv, traceFor(year), layout, { responsive: true, displayModeBar: false });
    const metric = firesByState.metric_by_year[String(year)];
    document.getElementById('state-map-note').innerHTML =
      `Showing <b>${metricLabels[metric] || metric}</b> for ${year}. ${firesByState.sources[metric]}`;
    document.querySelectorAll('#state-map-year-buttons button').forEach((b) => {
      b.classList.toggle('active', parseInt(b.dataset.year, 10) === year);
    });
    renderLegend(year);
  }

  function renderLegend(year) {
    const metric = firesByState.metric_by_year[String(year)];
    const label = metric === 'satellite_detections_firms' ? 'satellite fire detections' : 'wildfires reported';
    const legend = document.getElementById('state-map-legend');
    legend.innerHTML = `
      <div class="legend-title">${year} ${label}</div>
      <div class="legend-gradient" style="background:linear-gradient(90deg, #fdf0ec, #f5b8a3, #e37a5c, #c0392b, #6e1c12)"></div>
      <div class="legend-scale"><span>0</span><span>${fmtNum(globalMax)}+</span></div>
      <p class="small-note" style="margin-top:0.8rem">Darker = more ${label} that year. Color scale is fixed across all years (2020&ndash;2026) so shades are directly comparable when you switch years. Hover a state on the map for its exact count.</p>
    `;
  }

  // year buttons
  const btnRow = document.getElementById('state-map-year-buttons');
  btnRow.innerHTML = years.map((y) => `<button data-year="${y}">${y}${y === 2026 ? ' (partial)' : ''}</button>`).join('');
  btnRow.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedYear = parseInt(btn.dataset.year, 10);
      paint(selectedYear);
    });
  });

  paint(selectedYear);
}

// ---------------------------------------------------------------------------
// Section: big fire case studies
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
// Section 5: interactive map (v2 dense grid + site-demo surrogate model)
// ---------------------------------------------------------------------------
let leafletMap, marker, circle;

function initMap() {
  leafletMap = L.map('map').setView([39.8, -98.6], 4);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(leafletMap);
}

function setMapLocation(lat, lon) {
  if (marker) leafletMap.removeLayer(marker);
  if (circle) leafletMap.removeLayer(circle);
  marker = L.marker([lat, lon]).addTo(leafletMap);
  circle = L.circle([lat, lon], { radius: 14000, color: '#c0392b', fillOpacity: 0.1 }).addTo(leafletMap);
  leafletMap.setView([lat, lon], 9);
}

async function geocodeAddress(address) {
  // The US Census geocoder (geocoding.geo.census.gov) doesn't send CORS
  // headers, so it can't be called directly from browser JS on a static
  // site — every request fails with an opaque "failed to fetch" error.
  // Nominatim (OpenStreetMap's public geocoder, the same data source as
  // the Leaflet basemap already used on this page) does support direct
  // browser fetches, so it's used here instead.
  const url = 'https://nominatim.openstreetmap.org/search' +
    '?format=json&limit=1&addressdetails=0&countrycodes=us&q=' + encodeURIComponent(address);
  const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  if (!res.ok) throw new Error('Geocoder request failed');
  const json = await res.json();
  if (!json || json.length === 0) return null;
  const m = json[0];
  return { lat: parseFloat(m.lat), lon: parseFloat(m.lon), matchedAddress: m.display_name };
}

function nearestCell(lat, lon) {
  let best = null;
  let bestDist = Infinity;
  const cosLat = Math.cos((lat * Math.PI) / 180);
  for (const cell of state.gridIndex) {
    const clat = cell.lat_bin + 0.125;
    const clon = cell.lon_bin + 0.125;
    const dlat = lat - clat;
    const dlon = (lon - clon) * cosLat;
    const dist = Math.sqrt(dlat * dlat + dlon * dlon);
    if (dist < bestDist) { bestDist = dist; best = cell; }
  }
  return { cell: best, distDeg: bestDist, distMiles: bestDist * 69 };
}

function renderRiskLegend(bands) {
  const items = [
    { label: 'Typical', color: 'var(--typical)', upto: bands.typical_upper },
    { label: 'Moderate', color: 'var(--rmoderate)', upto: bands.moderate_upper },
    { label: 'Elevated', color: 'var(--elevated)', upto: bands.elevated_upper },
    { label: 'High', color: 'var(--rhigh)', upto: bands.high_upper },
    { label: 'Extreme', color: 'var(--extreme-band)', upto: null },
  ];
  document.getElementById('risk-legend').innerHTML = items.map((it) => `
    <span class="risk-legend-item">
      <span class="risk-legend-swatch" style="background:${it.color}"></span>
      ${it.label}${it.upto !== null ? ` (&le; ${fmtPct(it.upto, 2)})` : ` (&gt; ${fmtPct(bands.high_upper, 2)})`}
    </span>`).join('');
}

function causeTips(causeNames) {
  const tips = {
    'Human': 'Most human-caused ignitions are preventable: check local burn-ban status before any outdoor burning, fully extinguish campfires (stir, soak, stir again), and avoid dragging trailer chains or mowing dry grass on hot/windy days.',
    'Natural': 'Lightning-caused starts can\'t be prevented, but dry-lightning risk is a signal to have an evacuation plan ready and to clear defensible space around structures in advance.',
    'Debris and Open Burning': 'Skip debris burning on dry or windy days; check for local burn permits and burn bans first.',
    'Equipment and Vehicle Use': 'Keep spark arrestors maintained on equipment/vehicles, avoid off-road driving or parking over dry grass, and carry a fire extinguisher.',
    'Recreation and Ceremony': 'Fully extinguish campfires and coals, and avoid fireworks or sky lanterns in dry vegetation.',
    'Arson': 'Report unattended or suspicious fires immediately to local authorities.',
    'Railroad Operations': 'Rail-adjacent dry vegetation is a known ignition point after brake/wheel sparking; local agencies sometimes clear vegetation buffers along rail corridors.',
    'Power generation / transmission / distribution': 'In high-wind red-flag conditions, utilities may proactively shut off power (PSPS) in high-risk areas; sign up for utility wildfire-safety alerts if available in your area.',
    'Firearms and Explosives Use': 'Avoid target shooting with tracer/incendiary ammunition in dry vegetation.',
    'Fireworks': 'Avoid fireworks entirely in dry vegetation or during burn bans; many CA/AZ/CO/etc. counties ban all consumer fireworks during fire season.',
  };
  const out = [];
  for (const name of causeNames) if (tips[name]) out.push(tips[name]);
  if (out.length === 0) {
    out.push('Follow local fire restrictions, keep vegetation cleared 5-30 feet from structures, and have an evacuation plan ready during red-flag warning days.');
  }
  return out;
}

function renderCauses(gridId) {
  const causeData = state.cellCauses[gridId];
  if (!causeData) {
    return { html: '<p class="small-note">No nearby historical reported-cause data for this area.</p>', causeNames: [] };
  }
  const generalEntries = Object.entries(causeData.general).sort((a, b) => b[1] - a[1]);
  const causeNames = generalEntries.map((e) => e[0]);
  const html = `
    <ul>${generalEntries.map(([name, n]) => `<li><b>${name}</b> &mdash; ${n} of ${causeData.n_nearby_cases} nearby historically reported fires</li>`).join('')}</ul>
    <p class="small-note">Historical reported-cause context (not the satellite-only model's target), based on ${causeData.n_nearby_cases} incidents within ~140 miles.</p>
  `;
  return { html, causeNames };
}

function dateOffset(a, b) {
  return (new Date(a) - new Date(b)) / 86400000;
}

async function handleLookup() {
  const address = document.getElementById('address-input').value.trim();
  const dateStr = document.getElementById('date-input').value;
  const statusEl = document.getElementById('lookup-status');
  const panel = document.getElementById('result-panel');
  if (!address) { statusEl.textContent = 'Enter a U.S. address first.'; return; }
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
      statusEl.textContent = 'Could not reach the geocoding service (OpenStreetMap/Nominatim). If this persists, try entering coordinates directly as "lat, lon".';
      return;
    }
  }
  if (!geo) {
    statusEl.textContent = 'No match found for that address. Try adding city and state, or enter coordinates as "lat, lon".';
    return;
  }
  if (geo.lat < 24 || geo.lat > 50 || geo.lon < -125 || geo.lon > -66) {
    statusEl.textContent = 'This model version only covers the continental U.S. (GridMET land coverage). Try a CONUS address.';
    return;
  }
  statusEl.textContent = `Matched: ${geo.matchedAddress}`;
  setMapLocation(geo.lat, geo.lon);

  const { cell, distMiles } = nearestCell(geo.lat, geo.lon);
  const cutoff = state.featureMeta.cutoff_date;
  const isPast = dateStr <= cutoff;
  const farAway = distMiles > 20;

  let bodyHtml = '';
  const causes = renderCauses(cell.grid_id);

  if (farAway) {
    bodyHtml += `<p class="small-note">The nearest dense 0.25&deg; grid cell is ~${Math.round(distMiles)} miles away, so this is a regional approximation.</p>`;
  }

  if (isPast) {
    const events = state.dailyEvents[cell.grid_id] || {};
    const dayEvent = events[dateStr];
    let detailHtml = '';
    let hasActivity = false;
    if (dayEvent) {
      hasActivity = true;
      detailHtml = `
        <ul>
          <li>Satellite (MODIS/VIIRS) detections that day: <b>${dayEvent.fire_count}</b>${dayEvent.total_frp ? `, total fire radiative power ${dayEvent.total_frp}` : ''}</li>
        </ul>`;
    } else {
      const nearby = Object.keys(events).filter((d) => Math.abs(dateOffset(d, dateStr)) <= 14).sort();
      detailHtml = nearby.length
        ? `<p class="small-note">No detections on this exact date. Nearby recorded activity: ${nearby.slice(0, 5).join(', ')}.</p>`
        : '<p class="small-note">No satellite detections recorded at this location in our 2026 dataset.</p>';
    }
    bodyHtml += `
      <p class="source-tag">Observed data (ground truth), not a model prediction</p>
      <span class="risk-badge ${hasActivity ? 'risk-Elevated' : 'risk-Typical'}">${hasActivity ? 'Detected activity' : 'No detected activity'}</span>
      ${detailHtml}
    `;
  } else {
    const cellState = state.cellState[cell.grid_id];
    const featureVec = buildFutureFeatureVector(
      state.featureMeta.feature_cols, { ...cellState, ...cell }, dateStr, cutoff,
      state.climatology, state.featureMeta.col_medians
    );
    const riskIdx = state.forestRisk.classes.indexOf('1');
    const pRaw = forestPredictProba(state.forestRisk, featureVec)[riskIdx === -1 ? state.forestRisk.classes.indexOf('1.0') : riskIdx];
    const proba = calibrateBalancedProba(pRaw, state.featureMeta.weighted_prevalence, state.featureMeta.balanced_train_prior);
    const band = riskBandFromProbability(proba, state.riskBands);
    bodyHtml += `
      <p class="source-tag">Site-demo random-forest prediction (holdout ROC AUC ${state.featureMeta.holdout_auc.toFixed(2)}) &mdash; rescaled from the model's balanced training prior back to a realistic probability, then bucketed with the real project model's risk bands</p>
      <span class="risk-badge risk-${band.label}">${band.label} risk &middot; ${fmtPct(proba, 3)}</span>
      <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${Math.min(100, proba * 1000)}%"></div></div>
      <ul>
        <li>Modeled probability of a new satellite-detected ignition the following day: <b>${fmtPct(proba, 3)}</b></li>
        <li>Real project model's "typical" upper bound for comparison: <b>${fmtPct(state.riskBands.typical_upper, 3)}</b></li>
      </ul>
      <p class="small-note">Future-date estimate assumes no new fire activity between the data cutoff (${cutoff}) and this date, and uses a seasonal weather estimate rather than a real forecast.</p>
    `;
  }

  bodyHtml += `<h4>Historical reported causes nearby</h4>${causes.html}`;
  const tips = causeTips(causes.causeNames);
  bodyHtml += `<h4>Prevention steps</h4><ul>${tips.map((t) => `<li>${t}</li>`).join('')}</ul>`;
  bodyHtml += renderLLMBox();

  panel.innerHTML = `<h3>${geo.matchedAddress}</h3>` + bodyHtml;
  wireLLMBox({ address: geo.matchedAddress, dateStr, isPast, cell, causes });
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
    `${ctx.isPast ? 'Based on recorded satellite data' : 'Based on the site-demo random-forest model'} for the nearest 0.25-degree grid cell, ` +
    `see the risk badge and cause list above. To prevent human-caused ignition: avoid open burning on dry/windy days, ` +
    `fully extinguish campfires and coals, keep equipment spark arrestors maintained, and follow any local burn bans or fire restrictions.`;
}

function wireLLMBox(ctx) {
  const btn = document.getElementById('generate-report-btn');
  const out = document.getElementById('llm-report');
  out.textContent = templateReport(ctx);
  btn.addEventListener('click', async () => {
    const key = document.getElementById('openai-key').value.trim();
    if (!key) { out.textContent = templateReport(ctx); return; }
    out.textContent = 'Generating…';
    try {
      const prompt = `You are a wildfire risk assistant for local communities. Using ONLY the context below ` +
        `(no outside knowledge of current events), write a concise (under 100 words) plain-English report covering: ` +
        `likelihood of fire, likely causes, and concrete human-caused-ignition prevention steps.\n\n` +
        `Location: ${ctx.address}\nDate: ${ctx.dateStr}\nData type: ${ctx.isPast ? 'observed satellite record' : 'random-forest model prediction'}\n` +
        `Nearby historical causes: ${ctx.causes.causeNames.join(', ') || 'unknown'}`;
      const res = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
        body: JSON.stringify({ model: 'gpt-4o-mini', messages: [{ role: 'user', content: prompt }], max_tokens: 220 }),
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
// Section 6: REAL model analysis (from improved_artifacts, not the demo model)
// ---------------------------------------------------------------------------
const FEATURE_LABELS = {
  lat: 'Latitude', lon: 'Longitude', month: 'Month', sin_doy: 'Season (sin)', cos_doy: 'Season (cos)',
  tmmx: 'Max temperature (GridMET)', tmmn: 'Min temperature (GridMET)', pr: 'Precipitation (GridMET)',
  vs: 'Wind speed (GridMET)', rmin: 'Min relative humidity (GridMET)', vpd: 'Vapor pressure deficit',
  erc: 'Energy release component', fm100: '100-hr dead fuel moisture',
  fire_count_lag_1d: 'Satellite detections, last 1 day', frp_lag_1d: 'Fire radiative power, last 1 day',
  fire_count_lag_3d: 'Satellite detections, last 3 days', frp_lag_3d: 'Fire radiative power, last 3 days',
  fire_count_lag_7d: 'Satellite detections, last 7 days', frp_lag_7d: 'Fire radiative power, last 7 days',
  fire_count_lag_14d: 'Satellite detections, last 14 days', frp_lag_14d: 'Fire radiative power, last 14 days',
  population_per_sq_km: 'Population density', primary_road_km_per_100_sq_km: 'Road density',
  log_population_density: 'Log population density', distance_to_fire_station_km: 'Distance to fire/EMS station',
};
function labelFor(f) { return FEATURE_LABELS[f] || f; }

// ---------------------------------------------------------------------------
// Section 2.5: why machine learning (live stats pulled from the real model's
// own evaluated performance, not separately-hardcoded numbers)
// ---------------------------------------------------------------------------
function renderWhyMLSection(m) {
  const testSplit = m.metrics_by_split.find((s) => s.split === 'temporal_test') || m.metrics_by_split[0];
  const ab = m.coordinate_ablation;
  const full = ab.find((r) => r.feature_strategy === 'full');
  const conditionsOnly = ab.find((r) => r.feature_strategy === 'conditions_only');
  const skillDrop = full && conditionsOnly ? (1 - conditionsOnly.PR_AUC / full.PR_AUC) : null;

  const kpis = [
    {
      title: 'Lift at top 1% of cells',
      value: testSplit.lift_top_1pct.toFixed(1) + '×',
      note: 'more real ignitions found there than chance would predict',
    },
    {
      title: 'Catch rate on a 5% alert budget',
      value: fmtPct(testSplit.alert_budget_5pct_recall, 0),
      note: `of real ignitions, watching only ${fmtPct(testSplit.alert_budget_5pct_flagged_fraction, 1)} of all grid-days`,
    },
    {
      title: 'Skill lost using only location + season',
      value: skillDrop !== null ? '−' + fmtPct(skillDrop, 0) : '–',
      note: 'drop in PR AUC without real fire-weather or activity signals',
    },
  ];
  document.getElementById('why-ml-kpis').innerHTML = kpis.map((k) => `
    <div class="kpi-card"><div class="kpi-title">${k.title}</div><div class="kpi-value">${k.value}</div><div class="kpi-note">${k.note}</div></div>`).join('');

  document.getElementById('why-ml-callout').innerHTML =
    `In the real project model's own held-out evaluation: the riskiest 1% of grid-cell-days contain <b>${testSplit.lift_top_1pct.toFixed(1)}&times;</b> ` +
    `as many real ignitions as you'd expect by chance, and watching just the riskiest <b>${fmtPct(testSplit.alert_budget_5pct_flagged_fraction, 1)}</b> of all ` +
    `grid-days still catches <b>${fmtPct(testSplit.alert_budget_5pct_recall, 0)}</b> of the ignitions that actually happened. ` +
    (skillDrop !== null ? `Strip out real fire-weather and recent-activity data and keep only location and season, and predictive skill (PR AUC) drops by <b>${fmtPct(skillDrop, 0)}</b> &mdash; concrete evidence the model is learning from real conditions, not just memorizing where fires usually are.` : '');
}

function renderModelAnalysis(m) {
  const card = m.model_card;
  document.getElementById('model-card-summary').innerHTML =
    `Winning model: <b>${card.model_name}</b> (${card.calibration_method} calibration, "${card.feature_strategy}" feature set). ` +
    `Target: <i>${card.label}</i>, at ${card.grid_degrees}&deg; resolution, ${card.decision_horizon_days}-day horizon, ${card.geographic_scope}. ` +
    `Trained ${card.training_years.join('–')}, calibrated on ${card.calibration_year}, tested on ${card.test_years.join(', ')}.`;

  const sv = card.selected_validation_metrics;
  const testSplit = m.metrics_by_split.find((s) => s.split === 'temporal_test') || m.metrics_by_split[0];
  const kpis = [
    { title: 'ROC AUC', value: sv.ROC_AUC.toFixed(3), note: 'held-out validation' },
    { title: 'PR AUC', value: sv.PR_AUC.toFixed(4), note: 'precision-recall, rare-event aware' },
    { title: 'Brier score', value: sv.Brier.toFixed(5), note: 'lower is better calibrated' },
    { title: 'Lift @ top 1%', value: testSplit.lift_top_1pct.toFixed(1) + '×', note: 'vs. random baseline' },
    { title: 'Recall @ 80% target', value: fmtPct(testSplit.recall_80_recall, 0), note: `flags ${fmtPct(testSplit.recall_80_flagged_fraction, 1)} of all cell-days` },
    { title: 'Test positives', value: fmtNum(testSplit.positives), note: `of ${fmtNum(testSplit.rows)} held-out rows` },
  ];
  document.getElementById('kpi-cards').innerHTML = kpis.map((k) => `
    <div class="kpi-card"><div class="kpi-title">${k.title}</div><div class="kpi-value">${k.value}</div><div class="kpi-note">${k.note}</div></div>`).join('');

  // ---- 02: split summary (rows/positives per holdout split) ----
  const splitLabel = { calibration: 'Calibration (2024)', temporal_test: 'Temporal test (2025)', spatial_test: 'Spatial test (unseen blocks)' };
  document.getElementById('split-summary-table').innerHTML = `
    <tr><th>Split</th><th>Rows</th><th>Positives</th><th>Weighted prevalence</th></tr>
    ${m.metrics_by_split.map((s) => `<tr><td>${splitLabel[s.split] || s.split}</td><td>${fmtNum(s.rows)}</td><td>${fmtNum(s.positives)}</td><td>${fmtPct(s.positives / s.rows, 2)} (sampled; true population rate is lower)</td></tr>`).join('')}
  `;

  // ---- 03: candidate model leaderboard ----
  const candidates = [...m.candidate_results].sort((a, b) => b.PR_AUC - a.PR_AUC);
  document.getElementById('candidate-table').innerHTML = `
    <tr><th>Model</th><th>Feature set</th><th>Calibration</th><th>PR AUC</th><th>ROC AUC</th><th>Brier</th></tr>
    ${candidates.map((r, i) => {
      const isWinner = r.model === card.model_name && r.feature_strategy === card.feature_strategy && r.calibration === card.calibration_method;
      const row = `<td>${r.model.replace(/_/g, ' ')}</td><td>${r.feature_strategy.replace(/_/g, ' ')}</td><td>${r.calibration}</td><td>${r.PR_AUC.toFixed(4)}</td><td>${r.ROC_AUC.toFixed(3)}</td><td>${r.Brier.toFixed(5)}</td>`;
      return isWinner ? `<tr style="background:var(--accent-soft);font-weight:700"><td>&#9733; ${r.model.replace(/_/g, ' ')}</td><td>${r.feature_strategy.replace(/_/g, ' ')}</td><td>${r.calibration}</td><td>${r.PR_AUC.toFixed(4)}</td><td>${r.ROC_AUC.toFixed(3)}</td><td>${r.Brier.toFixed(5)}</td></tr>` : `<tr>${row}</tr>`;
    }).join('')}
  `;

  // ---- 04: full metrics-by-split table ----
  document.getElementById('split-metrics-table').innerHTML = `
    <tr><th>Split</th><th>ROC AUC</th><th>PR AUC</th><th>Brier</th><th>ECE (15-bin)</th><th>Lift @ top 1%</th><th>Lift @ top 5%</th></tr>
    ${m.metrics_by_split.map((s) => `<tr><td>${splitLabel[s.split] || s.split}</td><td>${s.ROC_AUC.toFixed(3)}</td><td>${s.PR_AUC.toFixed(4)}</td><td>${s.Brier.toFixed(5)}</td><td>${s.ECE_15.toFixed(4)}</td><td>${s.lift_top_1pct.toFixed(1)}&times;</td><td>${s.lift_top_5pct.toFixed(1)}&times;</td></tr>`).join('')}
  `;

  // ---- 04: threshold operating points, per split ----
  const thresholdRows = [];
  m.metrics_by_split.forEach((s) => {
    thresholdRows.push({ split: splitLabel[s.split] || s.split, name: 'Recall-80 target', precision: s.recall_80_precision, recall: s.recall_80_recall, flagged: s.recall_80_flagged_fraction, farate: s.recall_80_false_alarm_rate });
    thresholdRows.push({ split: splitLabel[s.split] || s.split, name: '5% alert budget', precision: s.alert_budget_5pct_precision, recall: s.alert_budget_5pct_recall, flagged: s.alert_budget_5pct_flagged_fraction, farate: s.alert_budget_5pct_false_alarm_rate });
  });
  document.getElementById('threshold-table').innerHTML = `
    <tr><th>Split</th><th>Operating point</th><th>Precision</th><th>Recall</th><th>Flagged fraction</th><th>False alarm rate</th></tr>
    ${thresholdRows.map((r) => `<tr><td>${r.split}</td><td>${r.name}</td><td>${fmtPct(r.precision, 1)}</td><td>${fmtPct(r.recall, 1)}</td><td>${fmtPct(r.flagged, 1)}</td><td>${fmtPct(r.farate, 1)}</td></tr>`).join('')}
  `;

  // ---- 05: permutation + SHAP importance tables ----
  const perm = [...m.permutation_importance].sort((a, b) => b.importance_mean - a.importance_mean).slice(0, 10);
  document.getElementById('perm-importance-table').innerHTML = `
    <tr><th>Feature</th><th>Importance</th></tr>
    ${perm.map((r) => `<tr><td>${r.feature}</td><td>${r.importance_mean.toFixed(4)} &plusmn; ${r.importance_std.toFixed(4)}</td></tr>`).join('')}
  `;
  const shap = [...m.shap_importance].sort((a, b) => b.mean_absolute_shap - a.mean_absolute_shap).slice(0, 10);
  document.getElementById('shap-importance-table').innerHTML = `
    <tr><th>Feature</th><th>Mean |SHAP|</th></tr>
    ${shap.map((r) => `<tr><td>${r.feature}</td><td>${r.mean_absolute_shap.toFixed(4)}</td></tr>`).join('')}
  `;

  const ab = m.coordinate_ablation;
  document.getElementById('ablation-table').innerHTML = `
    <tr><th>Feature set</th><th>PR AUC</th><th>ROC AUC</th><th>Brier</th></tr>
    ${ab.map((r) => `<tr><td>${r.feature_strategy.replace(/_/g, ' ')}</td><td>${r.PR_AUC.toFixed(4)}</td><td>${r.ROC_AUC.toFixed(3)}</td><td>${r.Brier.toFixed(5)}</td></tr>`).join('')}
  `;
  const full = ab.find((r) => r.feature_strategy === 'full');
  const noCoord = ab.find((r) => r.feature_strategy === 'no_coordinates');
  const condOnly = ab.find((r) => r.feature_strategy === 'conditions_only');
  if (full && noCoord && condOnly) {
    const dropNoCoord = 1 - noCoord.PR_AUC / full.PR_AUC;
    const dropCondOnly = 1 - condOnly.PR_AUC / full.PR_AUC;
    document.getElementById('ablation-callout').innerHTML =
      `Dropping <code>lat</code>/<code>lon</code> alone (<b>no_coordinates</b>) costs <b>${fmtPct(dropNoCoord, 1)}</b> of PR AUC. ` +
      `Keeping only fire-weather and history (<b>conditions_only</b>, also excluding month/day-of-year) costs <b>${fmtPct(dropCondOnly, 1)}</b>. ` +
      `Both drops are real but modest &mdash; location helps, but the bulk of predictive power survives without it, meaning the model leans on ` +
      `actual weather and recent-activity signals rather than simply memorizing fire-prone places.`;
  }

  // ---- 06: bootstrap + risk bands ----
  const ci = m.bootstrap_ci;
  document.getElementById('bootstrap-cards').innerHTML = ['ROC_AUC', 'PR_AUC', 'Brier'].map((key) => {
    const c = ci[key];
    const digits = key === 'PR_AUC' || key === 'Brier' ? 4 : 3;
    return `<div class="kpi-card"><div class="kpi-title">${key.replace('_', ' ')}</div><div class="kpi-value">${c.median.toFixed(digits)}</div><div class="kpi-note">95% CI ${c.lower_95.toFixed(digits)}–${c.upper_95.toFixed(digits)}</div></div>`;
  }).join('');

  const rb = card.risk_bands;
  const bands = [
    { name: 'Typical', lo: 0, hi: rb.typical_upper },
    { name: 'Moderate', lo: rb.typical_upper, hi: rb.moderate_upper },
    { name: 'Elevated', lo: rb.moderate_upper, hi: rb.elevated_upper },
    { name: 'High', lo: rb.elevated_upper, hi: rb.high_upper },
    { name: 'Extreme', lo: rb.high_upper, hi: null },
  ];
  document.getElementById('risk-band-table').innerHTML = `
    <tr><th>Band</th><th>Calibrated probability range</th></tr>
    ${bands.map((b) => `<tr><td><span class="risk-badge risk-${b.name}" style="font-size:0.78rem">${b.name}</span></td><td>${fmtPct(b.lo, 2)} &ndash; ${b.hi === null ? 'and above' : fmtPct(b.hi, 2)}</td></tr>`).join('')}
  `;

  document.getElementById('limitations-box').innerHTML = `
    <h4>Known limitations (from the model card)</h4>
    <ul>${card.limitations.map((l) => `<li>${l}</li>`).join('')}</ul>
  `;
  document.getElementById('next-steps-box').innerHTML = `
    <h4>Next recommended research steps (from the notebook's own discussion)</h4>
    <ul>
      <li>Prospective, forward-looking validation against fires as they happen, not just retrospective holdouts.</li>
      <li>Independent review by domain/fire-science experts before any operational use.</li>
      <li>Extend beyond the continental U.S. (GridMET's coverage limit) to Alaska, Hawaii, and other regions.</li>
      <li>Model fire spread and behavior, not just next-day detection onset.</li>
      <li>Incorporate additional data sources (e.g. finer-resolution fuels data, real-time human activity signals).</li>
      <li>Continue monitoring calibration drift as new years of data arrive, especially for partial/provisional 2026 data.</li>
    </ul>
  `;
}

// ---------------------------------------------------------------------------
// Scroll reveal + section nav dots (lightweight scrollytelling techniques)
// ---------------------------------------------------------------------------
function wireScrollEffects() {
  const reveals = document.querySelectorAll('.reveal');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add('is-visible'); });
  }, { threshold: 0.12 });
  reveals.forEach((el) => io.observe(el));

  const sections = document.querySelectorAll('main > section[id]');
  const nav = document.getElementById('section-nav');
  nav.innerHTML = Array.from(sections).map((s) => `<a href="#${s.id}" data-id="${s.id}" title="${s.id}"></a>`).join('');
  const navLinks = nav.querySelectorAll('a');
  const navIo = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      const link = nav.querySelector(`a[data-id="${e.target.id}"]`);
      if (e.isIntersecting) {
        navLinks.forEach((l) => l.classList.remove('active'));
        link.classList.add('active');
      }
    });
  }, { threshold: 0.5 });
  sections.forEach((s) => navIo.observe(s));
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function main() {
  const [annual, bigFires, gridIndex, cellState, cellCauses, dailyEvents,
    forestRisk, featureMeta, climatology, modelAnalysis, annualLoss, firesByState] = await Promise.all([
    loadJSON('annual_stats.json'),
    loadJSON('big_fires.json'),
    loadJSON('grid_index.json'),
    loadJSON('cell_state.json'),
    loadJSON('cell_causes.json'),
    loadJSON('daily_events.json'),
    loadJSON('forest_risk.json'),
    loadJSON('feature_meta.json'),
    loadJSON('climatology.json'),
    loadJSON('improved_model_analysis.json'),
    loadJSON('annual_loss.json'),
    loadJSON('fires_by_state.json'),
  ]);
  Object.assign(state, {
    gridIndex, cellState, cellCauses, dailyEvents, forestRisk, featureMeta, climatology,
    riskBands: modelAnalysis.model_card.risk_bands,
  });

  renderLossSection(annualLoss, annual);
  renderStoryCharts(annual);
  renderStateMap(firesByState);
  renderCaseCards(bigFires);
  renderRiskLegend(state.riskBands);
  document.getElementById('cutoff-date-label').textContent = featureMeta.cutoff_date;
  initMap();
  renderWhyMLSection(modelAnalysis);
  wireScrollEffects();

  document.getElementById('lookup-btn').addEventListener('click', handleLookup);
  document.getElementById('address-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleLookup();
  });
}

// ---------------------------------------------------------------------------
// Boot: methodology page (separate page, just the real model analysis)
// ---------------------------------------------------------------------------
async function mainMethodology() {
  const modelAnalysis = await loadJSON('improved_model_analysis.json');
  renderModelAnalysis(modelAnalysis);
  wireScrollEffects();
}
