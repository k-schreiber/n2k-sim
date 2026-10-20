// Main controller + views.
import { api, Socket } from './api.js';
import {
  h, fmt, fmtTime, toast, call, numField, textField, switchField, selectField, sectionCard, Spark,
} from './ui.js';
import { createWindGauge, createCompass } from './gauge.js';

if (new URLSearchParams(location.search).has('mock')) await import('./mock.js');

// ---------------------------------------------------------------- state
const S = { state: null, sig: new Map(), view: null };
const sentOrVal = (g) => (g ? (g.sent ?? g.value) : null);
/** Signal value as the instruments would show it (sent if present, else simulated). */
const val = (name) => sentOrVal(S.sig.get(name));
const sim = (name) => (S.sig.get(name) ? S.sig.get(name).value : null);

// 10 minute history, sampled from state pushes every 2 s of sim time
const hist = { t: [], twd: [], tws: [], stw: [], lastRaw: null };
function pushHist(st) {
  const t = st.sim_time;
  if (t === undefined || t === null) return;
  const last = hist.t[hist.t.length - 1];
  if (last !== undefined && t < last) { hist.t.length = 0; hist.twd.length = 0; hist.tws.length = 0; hist.stw.length = 0; hist.lastRaw = null; }
  if (hist.t.length && t - hist.t[hist.t.length - 1] < 2) return;
  const twd = val('twd'), tws = val('tws'), stw = val('stw');
  if (twd === null && tws === null) return;
  let u = twd;
  if (twd !== null && hist.lastRaw !== null) {
    const prev = hist.twd[hist.twd.length - 1];
    u = prev + ((((twd - hist.lastRaw) % 360) + 540) % 360) - 180;
  }
  hist.lastRaw = twd;
  hist.t.push(t); hist.twd.push(u ?? 0); hist.tws.push(tws ?? 0); hist.stw.push(stw ?? 0);
  while (hist.t.length && t - hist.t[0] > 600) { hist.t.shift(); hist.twd.shift(); hist.tws.shift(); hist.stw.shift(); }
}

// ---------------------------------------------------------------- Dashboard
function buildApQuick() {
  let ap = {};
  const mode = selectField({
    label: 'Mode',
    options: [['heading', 'Heading'], ['twa', 'TWA'], ['motor', 'Motor']],
    commit: (v) => call('PATCH', '/api/scenario/autopilot', { mode: v }),
  });
  const targetLabel = h('label', { text: 'Target' });
  const target = numField({
    label: 'Target', min: -360, max: 360, step: 1, unit: '°', slider: false,
    commit: (v) => call('PATCH', '/api/scenario/autopilot', { [ap.mode === 'twa' ? 'twa' : 'heading']: v }),
  });
  const rpm = numField({
    label: 'Engine rpm', min: 0, max: 4000, step: 50, unit: 'rpm', slider: false,
    commit: (v) => call('PATCH', '/api/scenario/autopilot', { rpm: v }),
  });
  const adj = (d) => h('button', { class: 'btn', text: (d > 0 ? '+' : '−') + Math.abs(d), onclick: () => call('POST', '/api/autopilot/adjust', { delta: d }) });
  const el = h('section', { class: 'card ap' },
    h('div', { class: 'card-h' }, h('h3', { text: 'Autopilot' })),
    h('div', { class: 'card-b' }, mode.el, target.el, rpm.el,
      h('div', { class: 'btnrow' }, adj(-10), adj(-1), adj(1), adj(10)),
      h('div', { class: 'btnrow' },
        h('button', { class: 'btn', text: 'Tack', onclick: () => call('POST', '/api/autopilot/tack') }),
        h('button', { class: 'btn', text: 'Gybe', onclick: () => call('POST', '/api/autopilot/gybe') }))));
  const tl = target.el.querySelector('label');
  return {
    el,
    update(st) {
      ap = (st.scenario && st.scenario.autopilot) || {};
      const prev = mode.input.value;
      mode.set(ap.mode);
      const twaMode = ap.mode === 'twa';
      tl.textContent = twaMode ? 'Target TWA' : 'Target heading';
      target.set(twaMode ? ap.twa : ap.heading, prev !== ap.mode);
      rpm.el.style.display = ap.mode === 'motor' ? '' : 'none';
      rpm.set(ap.rpm);
      void targetLabel;
    },
  };
}

const dashboard = (() => {
  let wind, compass, tiles = [], sparks, ap;
  const TILES = [
    ['STW', 'kn', () => val('stw'), 2], ['SOG', 'kn', () => val('sog'), 2], ['COG', '°', () => val('cog'), 0],
    ['Depth', 'm', () => val('depth'), 1], ['Heel (roll)', '°', () => val('roll'), 1], ['Pitch', '°', () => val('pitch'), 1],
    ['Rudder', '°', () => val('rudder'), 1], ['Leeway', '°', () => val('leeway_calc'), 1],
    ['VMG wind', 'kn', () => val('vmg_wind'), 2], ['Polar', '%', () => val('performance'), 0],
    ['Engine', 'rpm', () => val('engine.rpm'), 0],
  ];
  return {
    id: 'dashboard', title: 'Dashboard',
    build(root) {
      const wg = h('div', { class: 'gwrap' });
      const cg = h('div', { class: 'gwrap' });
      wind = createWindGauge(wg);
      compass = createCompass(cg);
      const tileEls = TILES.map(([lab, unit]) => {
        const v = h('span', { class: 'tv', text: '—' });
        tiles.push(v);
        return h('div', { class: 'tile' }, h('span', { class: 'tk', text: lab }), v, h('span', { class: 'tu', text: unit }));
      });
      const cvs = ['twd', 'tws', 'stw'].map(() => h('canvas', { class: 'spark' }));
      sparks = [
        ['twd', new Spark(cvs[0], { color: '#5bc0eb', label: 'TWD', unit: '°', dec: 0, wrap: true, minSpan: 10 })],
        ['tws', new Spark(cvs[1], { color: '#f2c14e', label: 'TWS', unit: 'kn', dec: 1, minSpan: 4 })],
        ['stw', new Spark(cvs[2], { color: '#7bd88f', label: 'STW', unit: 'kn', dec: 1, minSpan: 2 })],
      ];
      ap = buildApQuick();
      root.append(
        h('div', { class: 'dash-top' },
          h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: 'Wind' })), wg),
          h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: 'Compass' })), cg),
          ap.el),
        h('div', { class: 'tiles' }, tileEls),
        h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: 'Last 10 minutes' })),
          h('div', { class: 'sparks' }, cvs)));
    },
    update(st) {
      const scn = st.scenario || {};
      wind.update({ awa: val('awa'), twa: val('twa'), aws: val('aws'), tws: val('tws'), twd: val('twd') });
      compass.update({
        heading: val('heading_true') ?? sim('boat.heading') ?? val('yaw'),
        cog: val('cog'),
        currentSet: sim('env.current_set') ?? (scn.current && scn.current.set),
        currentDrift: sim('env.current_drift') ?? (scn.current && scn.current.drift),
        waveDir: sim('env.wave_dir') ?? (scn.waves && scn.waves.enabled ? scn.waves.direction : null),
        waveHeight: sim('env.wave_height') ?? (scn.waves && scn.waves.height),
      });
      TILES.forEach(([, , get, d], i) => { tiles[i].textContent = fmt(get(), d); });
      for (const [k, sp] of sparks) sp.draw(hist.t, hist[k]);
      ap.update(st);
    },
  };
})();

// ---------------------------------------------------------------- Environment
const environment = (() => {
  let cards = [], sparks = [];
  return {
    id: 'environment', title: 'Environment',
    build(root) {
      const gust = h('button', { class: 'btn primary', text: 'Gust now', onclick: () => call('POST', '/api/wind/gust', undefined, 'Gust triggered') });
      const cTwd = h('canvas', { class: 'spark' }), cTws = h('canvas', { class: 'spark' });
      sparks = [['twd', new Spark(cTwd, { color: '#5bc0eb', label: 'TWD', unit: '°', dec: 0, wrap: true, minSpan: 10 })],
        ['tws', new Spark(cTws, { color: '#f2c14e', label: 'TWS', unit: 'kn', dec: 1, minSpan: 4 })]];
      const wind = sectionCard('Wind', 'wind', [
        { key: 'fixed', label: 'Fixed', bool: true, header: true },
        { key: 'twd', label: 'Direction (TWD mean)', min: 0, max: 360, step: 1, unit: '°' },
        { key: 'tws', label: 'Speed (TWS mean)', min: 0, max: 60, step: 0.5, unit: 'kn' },
        { key: 'osc_amplitude', label: 'Oscillation amplitude', min: 0, max: 45, step: 0.5, unit: '°' },
        { key: 'osc_period_min', label: 'Oscillation period', min: 0.5, max: 30, step: 0.5, unit: 'min' },
        { key: 'shift_rate', label: 'Shift rate', min: 0, max: 5, step: 0.1, unit: '°/min' },
        { key: 'gust_interval_s', label: 'Gust interval', min: 0, max: 600, step: 5, unit: 's' },
        { key: 'gust_strength_pct', label: 'Gust strength', min: 0, max: 150, step: 1, unit: '%' },
        { key: 'gust_duration_s', label: 'Gust duration', min: 1, max: 120, step: 1, unit: 's' },
        { key: 'gust_veer', label: 'Gust veer', min: -30, max: 30, step: 0.5, unit: '°' },
        { key: 'lull_depth_pct', label: 'Lull depth', min: 0, max: 50, step: 1, unit: '%' },
      ], [h('div', { class: 'btnrow' }, gust), h('div', { class: 'minicharts' }, cTwd, cTws)]);
      const current = sectionCard('Current', 'current', [
        { key: 'fixed', label: 'Fixed', bool: true, header: true },
        { key: 'set', label: 'Set (flows to)', min: 0, max: 360, step: 1, unit: '°' },
        { key: 'drift', label: 'Drift', min: 0, max: 5, step: 0.05, unit: 'kn' },
        { key: 'tidal_amplitude_pct', label: 'Tidal amplitude', min: 0, max: 100, step: 1, unit: '%' },
        { key: 'tidal_period_h', label: 'Tidal period', min: 1, max: 24, step: 0.01, unit: 'h' },
      ]);
      const waves = sectionCard('Waves', 'waves', [
        { key: 'enabled', label: 'Enabled', bool: true, header: true },
        { key: 'direction', label: 'Direction (from)', min: 0, max: 360, step: 1, unit: '°' },
        { key: 'height', label: 'Height', min: 0, max: 8, step: 0.1, unit: 'm' },
        { key: 'period', label: 'Period', min: 2, max: 15, step: 0.1, unit: 's' },
        { key: 'irregularity', label: 'Irregularity', min: 0, max: 1, step: 0.01, unit: '' },
      ]);
      const seabed = sectionCard('Seabed', 'seabed', [
        { key: 'fixed', label: 'Fixed depth', bool: true, header: true },
        { key: 'depth', label: 'Depth (when fixed)', min: 1, max: 200, step: 0.5, unit: 'm' },
        { key: 'depth_min', label: 'Depth min', min: 1, max: 200, step: 0.5, unit: 'm' },
        { key: 'depth_max', label: 'Depth max', min: 1, max: 200, step: 0.5, unit: 'm' },
        { key: 'change_period_min', label: 'Change period', min: 0.5, max: 60, step: 0.5, unit: 'min' },
        { key: 'transducer_depth', label: 'Transducer depth', min: 0, max: 3, step: 0.05, unit: 'm' },
        { key: 'keel_depth', label: 'Keel depth', min: 0, max: 5, step: 0.05, unit: 'm' },
      ], [h('div', { class: 'btnrow' },
        h('button', { class: 'btn', text: 'Shallow patch', onclick: () => call('POST', '/api/seabed/shallow', undefined, 'Depth ramping to 3 m') }))]);
      cards = [wind, current, waves, seabed];
      root.append(h('div', { class: 'cards2' }, cards.map((c) => c.el)));
    },
    update(st) {
      for (const c of cards) c.update(st.scenario);
      for (const [k, sp] of sparks) sp.draw(hist.t, hist[k]);
    },
  };
})();

// ---------------------------------------------------------------- Boat
const boat = (() => {
  let cards = [], mode, apFields, lat, lon, polarBox, polarName = null, apCard, polarLoaded = false;
  const apDefs = [
    { key: 'heading', label: 'Heading target', min: 0, max: 360, step: 1, unit: '°' },
    { key: 'twa', label: 'TWA target (neg = port)', min: -180, max: 180, step: 1, unit: '°' },
    { key: 'rpm', label: 'Motor rpm', min: 0, max: 4000, step: 50, unit: 'rpm' },
  ];

  function polarDiagram(p) {
    const NS = 'http://www.w3.org/2000/svg';
    const mk = (t, a, par) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a || {})) e.setAttribute(k, v); if (par) par.append(e); return e; };
    const svg = mk('svg', { viewBox: '-150 -150 300 300', class: 'polar-svg' });
    const vmax = Math.max(...p.speed.flat(), 1);
    const top = Math.ceil(vmax / 2) * 2;
    const R = 130;
    const sc = R / top;
    for (let v = 2; v <= top; v += 2) {
      mk('circle', { r: v * sc, class: 'g-grid' }, svg);
      const t = mk('text', { x: 3, y: -v * sc - 2, class: 'g-lbl small' }, svg); t.textContent = v;
    }
    for (let a = 0; a <= 180; a += 30) {
      const x = R * Math.sin(a * Math.PI / 180), y = -R * Math.cos(a * Math.PI / 180);
      mk('line', { x1: 0, y1: 0, x2: x, y2: y, class: 'g-grid' }, svg);
      mk('line', { x1: 0, y1: 0, x2: -x, y2: y, class: 'g-grid' }, svg);
      const t = mk('text', { x: x * 1.08 + 2, y: y * 1.08 + 3, class: 'g-lbl small' }, svg); t.textContent = a;
    }
    p.tws.forEach((tws, j) => {
      const col = `hsl(${200 - (j * 170) / Math.max(1, p.tws.length - 1)} 70% 60%)`;
      const pts = p.twa.map((a, i) => [p.speed[i][j] * sc * Math.sin(a * Math.PI / 180), -p.speed[i][j] * sc * Math.cos(a * Math.PI / 180)]);
      mk('polyline', { points: pts.map((q) => q.join(',')).join(' '), fill: 'none', stroke: col, 'stroke-width': 1.6 }, svg);
      mk('polyline', { points: pts.map(([x, y]) => `${-x},${y}`).join(' '), fill: 'none', stroke: col, 'stroke-width': 1.6, opacity: 0.5 }, svg);
      const [lx, ly] = pts[pts.length - 1];
      const t = mk('text', { x: lx + 3, y: ly + 10, class: 'g-lbl small', fill: col }, svg); t.textContent = `${tws}kn`;
    });
    return svg;
  }

  async function loadPolar() {
    try {
      const p = await api('GET', '/api/polar');
      polarLoaded = true;
      polarName = p.name;
      const head = h('tr', {}, h('th', { text: 'TWA \\ TWS' }), p.tws.map((v) => h('th', { text: v })));
      const rows = p.twa.map((a, i) => h('tr', {}, h('th', { text: a }), p.speed[i].map((v) => h('td', { text: fmt(v, 1) }))));
      polarBox.replaceChildren(
        h('div', { class: 'muted', text: `Active polar: ${p.name}` }),
        h('div', { class: 'polar-wrap' },
          h('div', { class: 'tablewrap' }, h('table', { class: 'tbl compact' }, h('thead', {}, head), h('tbody', {}, rows))),
          polarDiagram(p)));
    } catch (e) { polarBox.replaceChildren(h('div', { class: 'muted', text: 'Polar unavailable: ' + e.message })); }
  }

  return {
    id: 'boat', title: 'Boat',
    build(root) {
      mode = selectField({
        label: 'Mode', options: [['heading', 'Heading'], ['twa', 'TWA'], ['motor', 'Motor']],
        commit: (v) => call('PATCH', '/api/scenario/autopilot', { mode: v }),
      });
      apCard = sectionCard('Autopilot', 'autopilot', apDefs, [mode.el]);
      apCard.el.querySelector('.card-b').prepend(mode.el);
      const boatCard = sectionCard('Boat', 'boat', [
        { key: 'leeway_k', label: 'Leeway K (boat)', min: 0, max: 30, step: 0.1, unit: '', hint: 'lambda = K * heel / STW^2' },
        { key: 'stw_time_constant_s', label: 'STW time constant', min: 1, max: 30, step: 0.5, unit: 's' },
        { key: 'max_turn_rate', label: 'Max turn rate', min: 1, max: 20, step: 0.5, unit: '°/s' },
        { key: 'motor_speed_per_1000rpm', label: 'Motor speed / 1000 rpm', min: 0.5, max: 6, step: 0.1, unit: 'kn' },
        { key: 'sail_roll_damping', label: 'Sail roll damping (full load)', min: 0, max: 1, step: 0.05, unit: '', hint: 'wave roll factor when sails are fully loaded; 1 = no damping' },
        { key: 'sail_damping_aws_ref', label: 'Full sail load at AWS', min: 1, max: 40, step: 0.5, unit: 'kn' },
      ]);
      const proc = sectionCard('Instrument processor', 'processor', [
        { key: 'leeway_k', label: 'Leeway K (instruments)', min: 0, max: 30, step: 0.1, unit: '' },
      ]);
      lat = textField({ label: 'Start latitude', type: 'number', step: 0.0001, unit: '°N', commit: () => {} });
      lon = textField({ label: 'Start longitude', type: 'number', step: 0.0001, unit: '°E', commit: () => {} });
      const pos = h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: 'Position' })),
        h('div', { class: 'card-b' }, lat.el, lon.el,
          h('div', { class: 'btnrow' },
            h('button', { class: 'btn', text: 'Apply / teleport', onclick: () => {
              const la = parseFloat(lat.input.value), lo = parseFloat(lon.input.value);
              if (!Number.isFinite(la) || !Number.isFinite(lo)) return toast('Invalid position', true);
              call('PATCH', '/api/scenario/boat', { lat: la, lon: lo }, 'Position applied');
            } }),
            h('button', { class: 'btn', text: 'Reset trip log', onclick: () => call('POST', '/api/log/reset_trip', undefined, 'Trip reset') }))));
      const gps = sectionCard('GPS', 'gps', [
        { key: 'variation', label: 'Magnetic variation (E+)', min: -30, max: 30, step: 0.1, unit: '°' },
        { key: 'altitude', label: 'Altitude', min: -10, max: 500, step: 0.5, unit: 'm' },
        { key: 'geoidal_separation', label: 'Geoidal separation', min: -100, max: 100, step: 0.5, unit: 'm' },
        { key: 'local_offset_min', label: 'Local time offset', min: -720, max: 840, step: 15, unit: 'min' },
        { key: 'hdop', label: 'HDOP', min: 0, max: 10, step: 0.1 },
        { key: 'vdop', label: 'VDOP', min: 0, max: 10, step: 0.1 },
        { key: 'pdop', label: 'PDOP', min: 0, max: 10, step: 0.1 },
        { key: 'tdop', label: 'TDOP', min: 0, max: 10, step: 0.1 },
        { key: 'sats_used', label: 'Satellites used', min: 0, max: 32, step: 1 },
        { key: 'sats_in_view', label: 'Satellites in view', min: 0, max: 32, step: 1 },
      ]);
      cards = [apCard, boatCard, proc, gps];
      polarBox = h('div', { class: 'muted', text: 'Loading polar…' });
      const file = h('input', { type: 'file', accept: '.pol,.txt,.csv,text/plain', hidden: true });
      file.addEventListener('change', async () => {
        const f = file.files[0]; file.value = '';
        if (!f) return;
        if (await call('PUT', '/api/polar', await f.text(), `Polar "${f.name}" uploaded`)) loadPolar();
      });
      const polar = h('section', { class: 'card wide' }, h('div', { class: 'card-h' }, h('h3', { text: 'Polar' }), h('div', { class: 'spacer' }),
        h('button', { class: 'btn', text: 'Upload .pol…', onclick: () => file.click() }), file),
      h('div', { class: 'card-b' }, polarBox));
      root.append(h('div', { class: 'cards2' }, apCard.el, boatCard.el, pos, proc.el, gps.el), polar);
    },
    enter() { loadPolar(); },
    update(st) {
      for (const c of cards) c.update(st.scenario);
      const scn = st.scenario || {};
      if (scn.autopilot) mode.set(scn.autopilot.mode);
      if (scn.boat) { lat.set(scn.boat.lat); lon.set(scn.boat.lon); if (polarLoaded && polarName && scn.boat.polar_file && polarName !== scn.boat.polar_file && !String(polarName).includes(scn.boat.polar_file)) { polarName = scn.boat.polar_file; loadPolar(); } }
    },
  };
})();

// ---------------------------------------------------------------- Static data
const staticView = (() => {
  let root, key = '', fields = new Map();
  const GROUPS = [['meteo', 'Meteo'], ['engine', 'Engine'], ['tanks', 'Tanks'], ['batteries', 'Batteries']];
  return {
    id: 'static', title: 'Static data',
    build(r) { root = h('div', { class: 'cards2' }); r.append(h('p', { class: 'muted', text: 'Values set here are transmitted as-is (UI units). GPS-related settings are on the Boat view.' }), root); },
    update(st) {
      const stat = (st.signals || []).filter((x) => x.layer === 'static');
      const k = stat.map((x) => x.name).join(',');
      if (k !== key) {
        key = k; fields = new Map(); root.replaceChildren();
        const groups = [...GROUPS];
        for (const x of stat) if (!groups.some(([g]) => g === x.group)) groups.push([x.group, x.group]);
        for (const [g, title] of groups) {
          const sigs = stat.filter((x) => x.group === g);
          if (!sigs.length) continue;
          const body = sigs.map((x) => {
            const f = numField({ label: x.label, unit: x.unit, slider: false, step: 'any', commit: (v) => call('PATCH', '/api/static', { [x.name]: v }) });
            fields.set(x.name, f);
            return f.el;
          });
          root.append(h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: title })), h('div', { class: 'card-b' }, body)));
        }
      }
      for (const x of stat) { const f = fields.get(x.name); if (f) f.set(x.value); }
    },
  };
})();

// ---------------------------------------------------------------- Signals
const signals = (() => {
  let tbody, key = '', rows = new Map(), layerSel, textIn, count;
  const focusedIn = (el) => el.contains(document.activeElement);
  function applyFilter() {
    const layer = layerSel.value, q = textIn.value.trim().toLowerCase();
    let n = 0;
    for (const [, r] of rows) {
      const ok = (layer === 'all' || r.sig.layer === layer) &&
        (!q || r.sig.name.toLowerCase().includes(q) || (r.sig.label || '').toLowerCase().includes(q) || (r.sig.group || '').toLowerCase().includes(q));
      r.tr.hidden = !ok; if (ok) n++;
    }
    count.textContent = `${n} / ${rows.size} signals`;
  }
  function makeRow(sg) {
    const r = { sig: sg };
    const sent = h('td', { class: 'num' }), simv = h('td', { class: 'num' });
    const cb = h('input', { type: 'checkbox' });
    const inp = h('input', { type: 'number', class: 'num ovr', step: 'any' });
    let touched = 0;
    const put = (v) => { touched = Date.now(); return call('PUT', `/api/overrides/${encodeURIComponent(sg.name)}`, { value: v }); };
    cb.addEventListener('change', () => {
      touched = Date.now();
      if (cb.checked) {
        let v = parseFloat(inp.value);
        if (!Number.isFinite(v)) { v = r.sig.value; inp.value = v; }
        put(v);
      } else call('DELETE', `/api/overrides/${encodeURIComponent(sg.name)}`);
    });
    inp.addEventListener('change', () => { const v = parseFloat(inp.value); if (Number.isFinite(v)) { cb.checked = true; put(v); } });
    const ovr = sg.layer === 'env' ? h('td', { class: 'dim', text: '—' }) : h('td', { class: 'ovr-cell' }, cb, inp);
    r.tr = h('tr', {}, h('td', {}, h('div', { class: 'sn', text: sg.name }), h('div', { class: 'muted small', text: sg.label })),
      h('td', {}, h('span', { class: 'badge ' + sg.layer, text: sg.layer })), simv, sent, h('td', { text: sg.unit || '' }),
      h('td', { class: 'small', text: (sg.pgns || []).join(', ') }), ovr);
    r.simv = simv; r.sent = sent; r.cb = cb; r.inp = inp; r.touched = () => touched;
    return r;
  }
  return {
    id: 'signals', title: 'Signals',
    build(root) {
      layerSel = h('select', { class: 'sel', onchange: () => applyFilter() },
        ['all', 'env', 'sensor', 'calc', 'static'].map((l) => h('option', { value: l, text: l === 'all' ? 'All layers' : l })));
      textIn = h('input', { type: 'search', class: 'txt', placeholder: 'Filter by name, label, group…', oninput: () => applyFilter() });
      count = h('span', { class: 'muted' });
      tbody = h('tbody');
      root.append(h('div', { class: 'toolbar' }, layerSel, textIn, count),
        h('div', { class: 'tablewrap tall' }, h('table', { class: 'tbl' },
          h('thead', {}, h('tr', {}, ['Signal', 'Layer', 'Simulated', 'Sent', 'Unit', 'PGN', 'Override'].map((t) => h('th', { text: t })))), tbody)));
    },
    update(st) {
      const list = st.signals || [];
      const k = list.map((x) => x.name + ':' + x.layer).join(',');
      if (k !== key) {
        key = k; rows = new Map(); tbody.replaceChildren();
        for (const sg of list) { const r = makeRow(sg); rows.set(sg.name, r); tbody.append(r.tr); }
        applyFilter();
      }
      for (const sg of list) {
        const r = rows.get(sg.name); if (!r) continue;
        r.sig = sg;
        const d = sg.unit === 'kn' || sg.unit === 'm' ? 2 : 1;
        r.simv.textContent = fmt(sg.value, d);
        r.sent.textContent = sg.layer === 'env' ? '—' : fmt(sg.sent ?? sg.value, d);
        r.tr.classList.toggle('overridden', !!sg.overridden);
        if (sg.layer !== 'env') {
          if (!focusedIn(r.tr) && Date.now() - r.touched() > 2000) {
            r.cb.checked = !!sg.overridden;
            r.inp.value = String(+Number(sg.sent ?? sg.value).toFixed(4));
          }
        }
      }
    },
  };
})();

// ---------------------------------------------------------------- Output
const raw = { lines: [], paused: false, dirty: false };
let output_render = () => {};
const output = (() => {
  let tr = {}, recorder, source, pgnBody, pgnKey = '', pgnRows = new Map(), tail, filterIn, pauseBtn, statusEls = {};
  const patchOut = (b) => call('PATCH', '/api/output', b);

  function transportCard(name, key, withClients) {
    const en = switchField({ label: 'Enabled', inline: true, commit: (v) => patchOut({ [key]: { enabled: v } }) });
    const host = textField({ label: 'Host / address', commit: (v) => patchOut({ [key]: { host: v } }) });
    const port = textField({ label: 'Port', type: 'number', step: 1, min: 1, max: 65535, commit: (v) => patchOut({ [key]: { port: v } }) });
    const status = h('span', { class: 'badge off', text: 'off' });
    const bps = h('span', { text: '0' }), cl = h('span', { text: '0' }), err = h('div', { class: 'err-text' });
    const el = h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: name }), h('div', { class: 'spacer' }), en.el),
      h('div', { class: 'card-b' }, host.el, port.el,
        h('div', { class: 'kv' }, h('span', { text: 'Status' }), status, h('span', { text: 'Bytes/s' }), bps,
          withClients ? h('span', { text: 'Clients' }) : null, withClients ? cl : null),
        err));
    tr[key] = { en, host, port, status, bps, cl, err };
    return el;
  }

  function filteredLines() {
    const q = filterIn.value.trim();
    if (!q) return raw.lines;
    if (/^\d+$/.test(q)) {
      const want = parseInt(q, 10);
      return raw.lines.filter((l) => { const p = linePgn(l); return p === want; });
    }
    const lq = q.toLowerCase();
    return raw.lines.filter((l) => l.toLowerCase().includes(lq));
  }
  function render() {
    raw.dirty = false;
    if (!tail) return;
    const near = tail.scrollHeight - tail.scrollTop - tail.clientHeight < 40;
    tail.textContent = filteredLines().join('\n');
    if (near) tail.scrollTop = tail.scrollHeight;
  }
  output_render = render;

  return {
    id: 'output', title: 'Output',
    build(root) {
      recorder = switchField({ label: 'Recorder (log YD RAW to file)', commit: (v) => patchOut({ recorder: v }) });
      const recPath = h('div', { class: 'muted small' });
      statusEls.recPath = recPath;
      source = textField({ label: 'Source address', type: 'number', step: 1, min: 0, max: 252, commit: (v) => patchOut({ source: v }), unit: '' });
      const srcHex = h('span', { class: 'muted small' }); statusEls.srcHex = srcHex;
      source.el.append(srcHex);
      const misc = h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', { text: 'General' })),
        h('div', { class: 'card-b' }, recorder.el, recPath, source.el, h('div', { class: 'kv' }, h('span', { text: 'Frames/s' }), (statusEls.fps = h('span', { text: '0' })))));
      pgnBody = h('tbody');
      const pgnTable = h('section', { class: 'card wide' }, h('div', { class: 'card-h' }, h('h3', { text: 'PGNs' })),
        h('div', { class: 'tablewrap' }, h('table', { class: 'tbl compact' },
          h('thead', {}, h('tr', {}, ['On', 'PGN', 'Name', 'Interval (s)', 'Frames/s', 'Last payload'].map((t) => h('th', { text: t })))), pgnBody)));
      tail = h('pre', { class: 'tail' });
      filterIn = h('input', { type: 'search', class: 'txt', placeholder: 'PGN number or text filter', oninput: render });
      pauseBtn = h('button', { class: 'btn', text: 'Pause', onclick: () => { raw.paused = !raw.paused; pauseBtn.textContent = raw.paused ? 'Resume' : 'Pause'; } });
      const rawCard = h('section', { class: 'card wide' }, h('div', { class: 'card-h' }, h('h3', { text: 'YD RAW tail' }), h('div', { class: 'spacer' }),
        filterIn, pauseBtn, h('button', { class: 'btn', text: 'Clear', onclick: () => { raw.lines.length = 0; render(); } })), tail);
      root.append(h('div', { class: 'cards2' }, transportCard('UDP', 'udp', false), transportCard('TCP', 'tcp', true), misc), pgnTable, rawCard);
    },
    enter() { socket.subscribe('raw'); render(); },
    leave() { socket.unsubscribe('raw'); },
    update(st) {
      const o = st.output || {};
      for (const key of ['udp', 'tcp']) {
        const t = tr[key], d = o[key] || {};
        t.en.set(d.enabled); t.host.set(d.host); t.port.set(d.port);
        const bad = !!d.error;
        t.status.textContent = bad ? 'error' : d.enabled ? 'active' : 'off';
        t.status.className = 'badge ' + (bad ? 'bad' : d.enabled ? 'ok' : 'off');
        t.bps.textContent = fmt(d.bytes_per_s, 0);
        t.cl.textContent = d.clients ?? 0;
        t.err.textContent = d.error || '';
      }
      const rec = o.recorder || {};
      recorder.set(typeof rec === 'object' ? rec.enabled : rec);
      statusEls.recPath.textContent = rec && rec.path ? `Recording to ${rec.path}` : '';
      const src = o.source ?? (st.scenario && st.scenario.output && st.scenario.output.source);
      source.set(src);
      statusEls.srcHex.textContent = typeof src === 'number' ? ` = 0x${src.toString(16).toUpperCase().padStart(2, '0')}` : '';
      statusEls.fps.textContent = fmt(o.frames_per_s, 1);
      const list = o.pgns || [];
      const k = list.map((p) => p.id).join(',');
      if (k !== pgnKey) {
        pgnKey = k; pgnRows = new Map(); pgnBody.replaceChildren();
        for (const p of list) {
          const en = h('input', { type: 'checkbox' });
          const iv = textField({ label: '', type: 'number', step: 'any', min: 0, width: '5.5em', commit: (v) => call('PATCH', `/api/output/pgns/${encodeURIComponent(p.id)}`, { interval_s: v }) });
          en.addEventListener('change', () => call('PATCH', `/api/output/pgns/${encodeURIComponent(p.id)}`, { enabled: en.checked }));
          const fps = h('td', { class: 'num' }), hex = h('td', { class: 'mono hex' });
          pgnRows.set(p.id, { en, iv, fps, hex });
          pgnBody.append(h('tr', {}, h('td', {}, en), h('td', { text: p.pgn }), h('td', { text: p.name }), h('td', {}, iv.input), fps, hex));
        }
      }
      for (const p of list) {
        const r = pgnRows.get(p.id); if (!r) continue;
        if (document.activeElement !== r.en) r.en.checked = !!p.enabled;
        r.iv.set(p.interval_s);
        r.fps.textContent = fmt(p.frames_per_s, 1);
        r.hex.textContent = p.last_hex || '';
      }
    },
  };
})();

/** Extract PGN from the CAN id (first 8-hex-digit token) of a YD RAW line. */
function linePgn(line) {
  const m = line.match(/\b([0-9A-Fa-f]{8})\b/);
  if (!m) return null;
  const id = parseInt(m[1], 16);
  const pf = (id >> 16) & 0xff;
  const dp = (id >> 24) & 0x3;
  const ps = (id >> 8) & 0xff;
  return (dp << 16) | (pf << 8) | (pf < 240 ? 0 : ps);
}

// ---------------------------------------------------------------- shell
const VIEWS = [dashboard, environment, boat, staticView, signals, output];
const ICONS = { dashboard: '◔', environment: '≈', boat: '⚓', static: '☰', signals: '≡', output: '⇄' };
const sections = new Map();

function showView(id) {
  const next = VIEWS.find((v) => v.id === id) || VIEWS[0];
  if (S.view === next) return;
  if (S.view && S.view.leave) S.view.leave();
  S.view = next;
  for (const [vid, el] of sections) el.hidden = vid !== next.id;
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.id === next.id);
  if (next.enter) next.enter();
  if (S.state) next.update(S.state);
}

function buildShell() {
  const nav = document.getElementById('nav');
  const main = document.getElementById('main');
  for (const v of VIEWS) {
    nav.append(h('a', { href: '#' + v.id, 'data-id': v.id }, h('span', { class: 'ico', text: ICONS[v.id] }), h('span', { class: 'lbl', text: v.title })));
    const sec = h('section', { class: 'view', id: 'view-' + v.id, hidden: true }, h('h2', { text: v.title }));
    v.build(sec);
    main.append(sec);
    sections.set(v.id, sec);
  }
  window.addEventListener('hashchange', () => showView(location.hash.slice(1)));
}

const $ = (id) => document.getElementById(id);
function updateTopbar(st) {
  const btn = $('btn-run');
  btn.innerHTML = st.running ? '&#9208; Pause' : '&#9654; Run';
  btn.classList.toggle('primary', !st.running);
  $('t-sim').textContent = fmtTime(st.sim_time);
  const o = st.output || {};
  $('t-fps').textContent = fmt(o.frames_per_s, 0);
  $('t-clients').textContent = (o.tcp && o.tcp.clients) ?? 0;
}

function onState(st) {
  S.state = st;
  S.sig = new Map((st.signals || []).map((x) => [x.name, x]));
  pushHist(st);
  updateTopbar(st);
  if (S.view) S.view.update(st);
}

function setConn(ok) {
  $('conn').className = 'conn ' + (ok ? 'on' : 'off');
  $('conn-text').textContent = ok ? 'live' : 'reconnecting…';
}

const socket = new Socket({
  onState,
  onRaw(lines) {
    if (raw.paused) return;
    raw.lines.push(...lines);
    if (raw.lines.length > 200) raw.lines.splice(0, raw.lines.length - 200);
    if (!raw.dirty && S.view === output) { raw.dirty = true; requestAnimationFrame(output_render); }
  },
  onStatus: setConn,
});

function wireTopbar() {
  $('btn-run').addEventListener('click', () => call('POST', S.state && S.state.running ? '/api/sim/pause' : '/api/sim/resume'));
  $('btn-reset').addEventListener('click', () => call('POST', '/api/sim/reset', undefined, 'Simulation reset'));
  $('btn-save').addEventListener('click', async () => {
    try {
      const scn = await api('GET', '/api/scenario');
      const a = h('a', { href: URL.createObjectURL(new Blob([JSON.stringify(scn, null, 2)], { type: 'application/json' })), download: 'scenario.json' });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) { toast(e.message, true); }
  });
  $('btn-load').addEventListener('click', () => $('file-load').click());
  $('file-load').addEventListener('change', async (ev) => {
    const f = ev.target.files[0]; ev.target.value = '';
    if (!f) return;
    let obj;
    try { obj = JSON.parse(await f.text()); } catch { return toast('Not valid JSON', true); }
    if (await call('PUT', '/api/scenario', obj, 'Scenario loaded')) {
      try { onState(await api('GET', '/api/state')); } catch { /* next push will do */ }
    }
  });
}

buildShell();
wireTopbar();
showView(location.hash.slice(1) || 'dashboard');
api('GET', '/api/state').then(onState).catch((e) => toast('Cannot load state: ' + e.message, true));
socket.connect();
window.addEventListener('resize', () => { if (S.state && S.view) S.view.update(S.state); });
