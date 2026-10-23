// Offline fake backend, active with ?mock. Replaces window.fetch for /api/* and window.WebSocket for /ws.
const UNIT = { deg360: '°', deg180: '°', kn: 'kn', pct: '%', m: 'm', s: 's', deg_per_min: '°/min', nm: 'nm', degc: '°C',
  latlon: '°', time: 's', min: 'min', none: '', hpa: 'hPa', rpm: 'rpm', bar: 'bar', v: 'V', lph: 'L/h', hours: 'h', l: 'L', a: 'A' };
// name|ui|layer|group|label|pgns
const DEFS = `env.gwd|deg360|env|wind|Ground wind direction
env.gws|kn|env|wind|Ground wind speed
env.current_set|deg360|env|current|Current set
env.current_drift|kn|env|current|Current drift
env.wave_dir|deg360|env|waves|Wave direction (from)
env.wave_height|m|env|waves|Wave height
env.wave_length|m|env|waves|Wavelength
env.depth|m|env|seabed|Depth below waterline
boat.heading|deg360|env|boat|True heading
boat.stw|kn|env|boat|Speed through water
boat.heel|deg180|env|boat|Heel
awa|deg180|sensor|wind|Apparent wind angle|130306
aws|kn|sensor|wind|Apparent wind speed|130306
heading_mag|deg360|sensor|compass|Magnetic heading|127250
pitch|deg180|sensor|compass|Pitch|127257
roll|deg180|sensor|compass|Roll|127257
rudder|deg180|sensor|steering|Rudder angle|127245
stw|kn|sensor|log|Speed through water|128259
water_temp|degc|sensor|log|Water temperature|130312
depth|m|sensor|depth|Depth below transducer|128267
lat|latlon|sensor|gps|Latitude|129025
lon|latlon|sensor|gps|Longitude|129025
cog|deg360|sensor|gps|Course over ground|129026
sog|kn|sensor|gps|Speed over ground|129026
hdop|none|sensor|gps|HDOP|129029
heading_true|deg360|calc|processor|True heading
leeway_calc|deg180|calc|processor|Leeway (calculated)
tws|kn|calc|processor|True wind speed|130306
twa|deg180|calc|processor|True wind angle|130306
twd|deg360|calc|processor|True wind direction|130306
vmg_wind|kn|calc|processor|VMG to wind
polar_speed|kn|calc|processor|Polar target speed
performance|pct|calc|processor|Polar performance
air_temp|degc|static|meteo|Air temperature|130311
pressure|hpa|static|meteo|Air pressure|130311
humidity|pct|static|meteo|Relative humidity|130311
cabin_temp|degc|static|meteo|Cabin temperature|130312
engine.rpm|rpm|static|engine|Engine speed|127488
engine.oil_pressure|bar|static|engine|Oil pressure|127489
engine.oil_temp|degc|static|engine|Oil temperature|127489
engine.coolant_temp|degc|static|engine|Coolant temperature|127489
engine.hours|hours|static|engine|Engine hours|127489
tank.fuel.level|pct|static|tanks|Fuel level|127505
tank.fuel.capacity|l|static|tanks|Fuel capacity|127505
tank.fresh_water1.level|pct|static|tanks|Fresh water 1 level|127505
battery.house.voltage|v|static|batteries|House battery voltage|127508
battery.house.current|a|static|batteries|House battery current|127508
battery.engine.voltage|v|static|batteries|Engine battery voltage|127508`
  .split('\n').map((l) => { const [name, ui, layer, group, label, pgns] = l.split('|'); return { name, ui, layer, group, label, pgns: pgns ? [+pgns] : [] }; });

const scenario = {
  seed: 1,
  wind: { fixed: false, twd: 300, tws: 12, osc_amplitude: 8, osc_period_min: 6, shift_rate: 0.5, gust_interval_s: 90, gust_strength_pct: 35, gust_duration_s: 20, gust_veer: 5, lull_depth_pct: 10 },
  current: { fixed: true, set: 135, drift: 0.5, tidal_amplitude_pct: 50, tidal_period_h: 12.42 },
  waves: { enabled: true, direction: 290, height: 1, period: 5, irregularity: 0.2 },
  seabed: { fixed: false, depth: 20, depth_min: 12, depth_max: 35, change_period_min: 5, transducer_depth: 0.5, keel_depth: 1.8 },
  boat: { lat: 43.48, lon: 16.4, polar_file: 'mock_cruiser_40.pol', leeway_k: 10, stw_time_constant_s: 8, max_turn_rate: 6, motor_speed_per_1000rpm: 2.6, sail_roll_damping: 0.35, sail_damping_aws_ref: 15 },
  autopilot: { mode: 'twa', heading: 0, twa: -45, rpm: 2200 },
  gps: { variation: 4.5, altitude: 2, geoidal_separation: 45, local_offset_min: 120, hdop: 0.8, vdop: 1.2, pdop: 1.4, tdop: 0.9, sats_used: 12, sats_in_view: 14 },
  processor: { leeway_k: 10 },
  static: { air_temp: 22, pressure: 1013.2, humidity: 65, cabin_temp: 24, 'engine.rpm': 0, 'engine.oil_pressure': 3.5, 'engine.oil_temp': 90, 'engine.coolant_temp': 80, 'engine.hours': 1250,
    'tank.fuel.level': 75, 'tank.fuel.capacity': 200, 'tank.fresh_water1.level': 60, 'battery.house.voltage': 12.6, 'battery.house.current': -4.2, 'battery.engine.voltage': 12.8 },
  overrides: {},
  output: { source: 35, udp: { enabled: true, host: '255.255.255.255', port: 2002 }, tcp: { enabled: true, host: '0.0.0.0', port: 2223 }, recorder: false, pgns: {} },
};
const pgnDefs = [[130306, 'apparent', 'Wind (apparent)', 0.1], [130306, 'true', 'Wind (true)', 0.1], [128259, 'stw', 'Speed (water)', 1], [129025, 'pos', 'Position, rapid', 0.1],
  [129026, 'cogsog', 'COG & SOG', 0.25], [127250, 'hdg', 'Vessel heading', 0.1], [127257, 'att', 'Attitude', 0.1], [128267, 'depth', 'Water depth', 1], [127245, 'rudder', 'Rudder', 0.1]]
  .map(([pgn, k, name, iv]) => ({ id: `${pgn}.${k}`, pgn, name, enabled: true, interval_s: iv, frames_per_s: 1 / iv, last_hex: '' }));
let running = true, simT = 0, polar = null, shallowUntil = 0, gustUntil = -1, recorder = false;
const out = { udp: { bytes: 5900 }, tcp: { bytes: 5900 } };

function rnd() { return Math.random(); }
function values() {
  const t = simT, w = scenario.wind, ap = scenario.autopilot;
  const gust = t < gustUntil ? 1 + 0.4 * Math.sin(Math.PI * (1 - (gustUntil - t) / 20)) : 1;
  const osc = w.fixed ? 0 : w.osc_amplitude * Math.sin((2 * Math.PI * t) / (w.osc_period_min * 60));
  const twd = (w.twd + osc + 360) % 360;
  const tws = w.tws * gust * (w.fixed ? 1 : 1 + 0.12 * Math.sin(t / 7) * w.lull_depth_pct / 10);
  const twaT = ap.mode === 'twa' ? ap.twa : -45;
  const hdg = ((ap.mode === 'twa' ? twd - twaT : ap.heading) + 360) % 360;
  const twa = ((twd - hdg + 540) % 360) - 180;
  const stw = Math.max(0, 0.5 * tws * Math.sin((Math.abs(twa) * Math.PI) / 180) ** 0.5 + 0.8);
  const aws = Math.hypot(tws * Math.sin(twa * Math.PI / 180), tws * Math.cos(twa * Math.PI / 180) + stw);
  const awa = (Math.atan2(tws * Math.sin(twa * Math.PI / 180), tws * Math.cos(twa * Math.PI / 180) + stw) * 180) / Math.PI;
  const heel = -Math.sign(twa) * Math.min(25, aws * 1.2);
  const lee = -Math.sign(twa) * Math.min(10, (10 * Math.abs(heel)) / Math.max(1, stw * stw));
  const depth = scenario.seabed.fixed ? scenario.seabed.depth : (scenario.seabed.depth_min + scenario.seabed.depth_max) / 2 + 8 * Math.sin(t / 60);
  const dep = t < shallowUntil ? 3 : depth;
  const cog = (hdg + lee + 3 + 360) % 360;
  const wvH = scenario.waves.enabled ? scenario.waves.height : 0;
  const v = {
    'env.gwd': twd, 'env.gws': tws, 'env.current_set': scenario.current.set, 'env.current_drift': scenario.current.drift,
    'env.wave_dir': scenario.waves.direction, 'env.wave_height': wvH, 'env.wave_length': 1.56 * scenario.waves.period ** 2, 'env.depth': dep,
    'boat.heading': hdg, 'boat.stw': stw, 'boat.heel': heel,
    awa, aws, heading_mag: (hdg - scenario.gps.variation + 360) % 360, pitch: 2 * wvH * Math.sin(t * 1.3), roll: heel + 3 * wvH * Math.sin(t * 1.1),
    rudder: 3 * Math.sin(t / 3), stw, water_temp: 19.4, depth: dep - 0.5, lat: scenario.boat.lat + t * 1e-5, lon: scenario.boat.lon + t * 1e-5,
    cog, sog: stw + 0.3, hdop: scenario.gps.hdop, heading_true: hdg, leeway_calc: lee, tws, twa, twd, vmg_wind: stw * Math.cos(twa * Math.PI / 180),
    polar_speed: stw * 1.04, performance: 96 + 3 * Math.sin(t / 9),
  };
  for (const [k, x] of Object.entries(scenario.static)) v[k] = x;
  return v;
}
function state() {
  const v = values();
  const signals = DEFS.map((d) => {
    const ov = scenario.overrides[d.name];
    const val = v[d.name] ?? 0;
    return { name: d.name, label: d.label, group: d.group, layer: d.layer, unit: UNIT[d.ui] ?? '', value: val,
      sent: d.layer === 'env' ? null : ov ?? val, overridden: ov !== undefined, pgns: d.pgns };
  });
  for (const p of pgnDefs) {
    const o = scenario.output.pgns[p.id] || {};
    p.enabled = o.enabled ?? true; p.interval_s = o.interval_s ?? p.interval_s;
    p.frames_per_s = p.enabled ? 1 / p.interval_s : 0;
    p.last_hex = Array.from({ length: 8 }, () => Math.floor(rnd() * 256).toString(16).padStart(2, '0').toUpperCase()).join(' ');
  }
  const o = scenario.output;
  const fps = pgnDefs.reduce((a, p) => a + p.frames_per_s, 0);
  return {
    type: 'state', running, sim_time: simT, utc: 1760000000 + simT, signals, scenario: JSON.parse(JSON.stringify(scenario)),
    output: { frames_per_s: fps, source: o.source,
      udp: { ...o.udp, bytes_per_s: o.udp.enabled ? fps * 22 : 0, error: null },
      tcp: { ...o.tcp, clients: 1, bytes_per_s: o.tcp.enabled ? fps * 22 : 0, error: o.tcp.port === 1 ? 'Permission denied' : null },
      recorder: { enabled: recorder, path: recorder ? '/tmp/rec.yd' : null }, pgns: pgnDefs.map((p) => ({ ...p })) },
  };
}
function makePolar() {
  const tws = [4, 6, 8, 10, 12, 14, 16, 20], twa = [40, 52, 60, 75, 90, 110, 135, 150, 165, 180];
  return { name: 'mock_cruiser_40.pol', tws, twa, speed: twa.map((a) => tws.map((w) => +(Math.min(w * 0.55, 8) * (0.45 + 0.5 * Math.sin((a * Math.PI) / 180) ** 0.6 * (a > 150 ? 0.8 : 1))).toFixed(2))) };
}
function merge(dst, src) { for (const [k, v] of Object.entries(src)) { if (v && typeof v === 'object' && !Array.isArray(v) && dst[k] && typeof dst[k] === 'object') merge(dst[k], v); else dst[k] = v; } }

function route(method, path, body) {
  let m;
  if (method === 'GET' && path === '/api/state') return state();
  if (method === 'GET' && path === '/api/scenario') return scenario;
  if (method === 'PUT' && path === '/api/scenario') { merge(scenario, JSON.parse(body)); return { ok: true }; }
  if ((m = path.match(/^\/api\/scenario\/(\w+)$/)) && method === 'PATCH') {
    if (!scenario[m[1]]) throw new Error('unknown section'); merge(scenario[m[1]], JSON.parse(body)); return { ok: true };
  }
  if (method === 'PATCH' && path === '/api/static') { Object.assign(scenario.static, JSON.parse(body)); return { ok: true }; }
  if ((m = path.match(/^\/api\/overrides\/(.+)$/))) {
    const n = decodeURIComponent(m[1]);
    if (method === 'PUT') scenario.overrides[n] = JSON.parse(body).value; else delete scenario.overrides[n];
    return { ok: true };
  }
  if (method === 'PATCH' && path === '/api/output') { const b = JSON.parse(body); for (const [k, v] of Object.entries(b)) { if (v && typeof v === 'object') merge(scenario.output[k], v); else scenario.output[k] = v; if (k === 'recorder') recorder = !!v; } return { ok: true }; }
  if ((m = path.match(/^\/api\/output\/pgns\/(.+)$/))) { const id = decodeURIComponent(m[1]); scenario.output.pgns[id] = { ...(scenario.output.pgns[id] || {}), ...JSON.parse(body) }; return { ok: true }; }
  if (path === '/api/wind/gust') { gustUntil = simT + 20; return { ok: true }; }
  if (path === '/api/seabed/shallow') { shallowUntil = simT + 60; return { ok: true }; }
  if (path === '/api/autopilot/adjust') {
    const d = JSON.parse(body).delta, ap = scenario.autopilot; const k = ap.mode === 'twa' ? 'twa' : 'heading';
    ap[k] = ap.mode === 'twa' ? ap[k] + d : (ap[k] + d + 360) % 360; return { ok: true };
  }
  if (path === '/api/autopilot/tack' || path === '/api/autopilot/gybe') { scenario.autopilot.twa *= -1; return { ok: true }; }
  if (path === '/api/log/reset_trip') return { ok: true };
  if (path === '/api/sim/pause') { running = false; return { ok: true }; }
  if (path === '/api/sim/resume') { running = true; return { ok: true }; }
  if (path === '/api/sim/reset') { simT = 0; return { ok: true }; }
  if (path === '/api/polar') { if (method === 'PUT') { polar = makePolar(); polar.name = 'uploaded.pol'; return { ok: true }; } return (polar = polar || makePolar()); }
  throw Object.assign(new Error(`mock: no route ${method} ${path}`), { status: 404 });
}

const realFetch = window.fetch.bind(window);
window.fetch = async (url, opts = {}) => {
  const u = new URL(url, location.href);
  if (!u.pathname.startsWith('/api/')) return realFetch(url, opts);
  await new Promise((r) => setTimeout(r, 30));
  try {
    const data = route((opts.method || 'GET').toUpperCase(), u.pathname, opts.body);
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e) {
    return new Response(JSON.stringify({ detail: e.message }), { status: e.status || 400 });
  }
};

// Synthetic `motion` message following docs/spec/web-ui.md: 1 m / 5 s waves from ~40 deg off the bow, ~15 deg heel.
let mockPhase = 0;
function motionMsg() {
  const A0 = scenario.waves.enabled ? scenario.waves.height : 0, per = scenario.waves.period || 5;
  const A = A0 / 2, len = 1.56 * per * per, k = (2 * Math.PI) / len, f = 1.6, irr = scenario.waves.irregularity, mu = 0.7;
  mockPhase = (mockPhase + (2 * Math.PI * 0.1) / per) % (2 * Math.PI * 1000);
  const d = [-Math.cos(mu), -Math.sin(mu)];
  const a1 = mockPhase, a2 = f * mockPhase + 0.7;
  const eta = A * (Math.cos(a1) + (irr / f) * Math.cos(a2));
  const s = A * k * (Math.sin(a1) + irr * Math.sin(a2));      // surface gradient at the boat = s * d
  const gx = s * d[0], gy = s * d[1];
  const heel = 0.26;
  return { type: 'motion', valid: true, t: simT, roll: heel - 0.8 * Math.atan(gy), pitch: 0.8 * Math.atan(gx), heel,
    yaw_wave: 0.02 * Math.sin(mockPhase / 3), heading: 4.4, leeway: 0.07, rudder: 0.05 * Math.sin(simT / 3), awa: -0.61, aws: 8.1, stw: 3.0, motoring: false,
    wave: { height: A0, length: len, period: per, mu, phase: mockPhase, irregularity: irr, secondary: f } };
}

class FakeSocket {
  constructor() {
    this.readyState = 0; this.raw = false; this.motion = false;
    setTimeout(() => { this.readyState = 1; this.onopen && this.onopen({}); }, 50);
    this.timer = setInterval(() => {
      if (running) simT += 0.25;
      this._emit(state());
      if (this.raw) {
        const ts = new Date().toISOString().slice(11, 23);
        const lines = Array.from({ length: 1 + Math.floor(rnd() * 4) }, () => {
          const p = pgnDefs[Math.floor(rnd() * pgnDefs.length)];
          const id = ((2 << 26) | (p.pgn << 8) | 0x23) >>> 0;
          const data = Array.from({ length: 8 }, () => Math.floor(rnd() * 256).toString(16).padStart(2, '0').toUpperCase()).join(' ');
          return `${ts} R ${id.toString(16).toUpperCase().padStart(8, '0')} ${data}`;
        });
        this._emit({ type: 'raw', lines });
      }
    }, 250);
    this.mtimer = setInterval(() => { if (this.motion) this._emit(motionMsg()); }, 100);
  }
  _emit(o) { this.onmessage && this.onmessage({ data: JSON.stringify(o) }); }
  send(s) { const m = JSON.parse(s); if (m.subscribe === 'raw') this.raw = true; if (m.unsubscribe === 'raw') this.raw = false; if (m.subscribe === 'motion') this.motion = true; if (m.unsubscribe === 'motion') this.motion = false; }
  close() { clearInterval(this.timer); clearInterval(this.mtimer); this.readyState = 3; this.onclose && this.onclose({}); }
}
window.WebSocket = FakeSocket;
console.info('[mock] fake backend active');
