// 3D yacht + sea widget (plain WebGL1, no dependencies).
//
// Boat frame (as in docs/spec/web-ui.md): x forward, y starboard, z up, origin on the waterline amidships.
// GL world frame used here: X = boat x (forward), Y = up (boat z), Z = starboard (boat y). This is right-handed,
// so the boat-frame -> GL map is simply (x, y, z) -> (x, z, y).

const TAU = Math.PI * 2;
const D2R = Math.PI / 180;
const PHASE_WRAP = TAU * 1000;     // backend wraps wave.phase modulo 2*pi*1000
const RENDER_DELAY_MS = 120;       // render slightly in the past so we can interpolate 10 Hz samples
const CAM_TARGET_Y = 5.5;
const SEA_HALF = 60, SEA_SEGS = 128;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, u) => a + (b - a) * u;
const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d);

// ------------------------------------------------------------------ matrices (column-major 4x4)
const M = {
  id: () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
  mul(a, b) {
    const o = new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
    return o;
  },
  translate(x, y, z) { const m = M.id(); m[12] = x; m[13] = y; m[14] = z; return m; },
  rotX(a) { const m = M.id(), c = Math.cos(a), s = Math.sin(a); m[5] = c; m[9] = -s; m[6] = s; m[10] = c; return m; },
  rotY(a) { const m = M.id(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[8] = s; m[2] = -s; m[10] = c; return m; },
  rotZ(a) { const m = M.id(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[4] = -s; m[1] = s; m[5] = c; return m; },
  /** Rotation about a unit axis (Rodrigues). */
  axisAngle(k, a) {
    const c = Math.cos(a), s = Math.sin(a), t = 1 - c, [x, y, z] = k;
    const m = M.id();
    m[0] = c + x * x * t; m[4] = x * y * t - z * s; m[8] = x * z * t + y * s;
    m[1] = y * x * t + z * s; m[5] = c + y * y * t; m[9] = y * z * t - x * s;
    m[2] = z * x * t - y * s; m[6] = z * y * t + x * s; m[10] = c + z * z * t;
    return m;
  },
  /** Apply rotation matrix r about the point p. */
  about(r, p) { return M.mul(M.translate(p[0], p[1], p[2]), M.mul(r, M.translate(-p[0], -p[1], -p[2]))); },
  perspective(fovy, aspect, n, f) {
    const m = new Float32Array(16), t = 1 / Math.tan(fovy / 2);
    m[0] = t / aspect; m[5] = t; m[10] = (f + n) / (n - f); m[11] = -1; m[14] = (2 * f * n) / (n - f);
    return m;
  },
  /** Returns { view, right, up, fwd } for a camera at eye looking at target (world up = +Y). */
  lookAt(eye, tgt) {
    const z = norm3(sub3(eye, tgt)), x = norm3(cross3([0, 1, 0], z)), y = cross3(z, x);
    const view = new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
      -dot3(x, eye), -dot3(y, eye), -dot3(z, eye), 1]);
    return { view, right: x, up: y, fwd: [-z[0], -z[1], -z[2]] };
  },
};
function sub3(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function dot3(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function cross3(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function norm3(a) { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; }

// ------------------------------------------------------------------ mesh building (boat-frame coordinates in)
const P = (p) => [p[0], p[2], p[1]];   // boat frame -> GL world
const COL = {
  hull: [0.93, 0.94, 0.95], stripe: [0.08, 0.12, 0.28], antifoul: [0.5, 0.14, 0.12], teak: [0.66, 0.5, 0.31],
  cockpit: [0.5, 0.38, 0.24], cabin: [0.95, 0.95, 0.94], window: [0.08, 0.1, 0.14], keel: [0.33, 0.35, 0.39],
  rudder: [0.3, 0.32, 0.36], spar: [0.78, 0.8, 0.82], sail: [0.98, 0.97, 0.92], jib: [0.94, 0.95, 0.96],
};

/** Accumulates flat-shaded triangles: 10 floats per vertex (pos3, normal3, rgba). Colour alpha 1 = oriented
 *  (normals flipped to point away from `ref`), alpha 0 = two-sided surface (sails, thin fins). */
class MeshBuilder {
  constructor() { this.v = []; this.ref = null; }
  tri(a, b, c, col) {
    const A = P(a), B = P(b), C = P(c);
    let n = cross3(sub3(B, A), sub3(C, A));
    const l = Math.hypot(n[0], n[1], n[2]);
    if (l < 1e-9) return;
    n = [n[0] / l, n[1] / l, n[2] / l];
    if (this.ref) {
      const g = [(A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3, (A[2] + B[2] + C[2]) / 3];
      if (dot3(n, sub3(g, P(this.ref))) < 0) n = [-n[0], -n[1], -n[2]];
    }
    const alpha = this.ref ? 1 : 0;
    for (const p of [A, B, C]) this.v.push(p[0], p[1], p[2], n[0], n[1], n[2], col[0], col[1], col[2], alpha);
  }
  quad(a, b, c, d, col) { this.tri(a, b, c, col); this.tri(a, c, d, col); }
  /** Axis-aligned box (boat frame). */
  box(x0, x1, y0, y1, z0, z1, col) {
    const p = (x, y, z) => [x, y, z];
    const c = [p(x0, y0, z0), p(x1, y0, z0), p(x1, y1, z0), p(x0, y1, z0), p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1)];
    this.hexa(c, col);
  }
  /** Hexahedron from 8 corners (bottom 0-3, top 4-7, same winding). */
  hexa(c, col) {
    this.quad(c[0], c[1], c[2], c[3], col); this.quad(c[4], c[5], c[6], c[7], col);
    this.quad(c[0], c[1], c[5], c[4], col); this.quad(c[1], c[2], c[6], c[5], col);
    this.quad(c[2], c[3], c[7], c[6], col); this.quad(c[3], c[0], c[4], c[7], col);
  }
  ellipsoid(cx, cy, cz, rx, ry, rz, col, nLon = 10, nLat = 6) {
    const pt = (i, j) => {
      const phi = -Math.PI / 2 + (Math.PI * j) / nLat, lam = (TAU * i) / nLon;
      return [cx + rx * Math.cos(phi) * Math.cos(lam), cy + ry * Math.cos(phi) * Math.sin(lam), cz + rz * Math.sin(phi)];
    };
    for (let i = 0; i < nLon; i++) for (let j = 0; j < nLat; j++) this.quad(pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1), col);
  }
  upload(gl) {
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(this.v), gl.STATIC_DRAW);
    return { buf, count: this.v.length / 10 };
  }
}

// ------------------------------------------------------------------ yacht geometry (40 ft, boat frame, waterline z = 0)
const MAST_X = 0.95, MAST_TOP = 18, BOOM_Z = 3.0, RUDDER_X = -5.1;
const TACK = [5.5, 0, 1.4], JIB_HEAD = [1.6, 0, 14.2], JIB_CLEW = [1.5, 0, 2.1];
const deckZ = (x) => 1.15 + 0.2 * (x / 6) ** 2;

function buildHull() {
  const m = new MeshBuilder();
  const X = [-6, -5.2, -4, -2.5, -1, 0.5, 2, 3.4, 4.6, 5.5, 6];
  const B = [1.5, 1.75, 1.93, 2.0, 2.0, 1.95, 1.75, 1.4, 0.95, 0.45, 0.04];
  const SEG = [COL.hull, COL.hull, COL.stripe, COL.antifoul, COL.antifoul, COL.antifoul, COL.antifoul, COL.antifoul, COL.stripe, COL.hull, COL.hull];
  const FRAC = [1, 1, 0.99, 0.98, 0.8, 0.35];
  const rings = X.map((x, i) => {
    const zd = deckZ(x), hd = Math.max(0.3, 0.55 * (1 - 0.5 * ((x + 1) / 7) ** 2));
    const zs = [zd, 0.5, 0.08, -0.07, -hd * 0.6, -hd];
    const side = zs.map((z, j) => [FRAC[j] * B[i], z]);
    return [...side, ...side.slice().reverse().map(([y, z]) => [-y, z])].map(([y, z]) => [x, y, z]);
  });
  m.ref = [0, 0, 0.4];
  for (let i = 0; i < X.length - 1; i++) {
    for (let k = 0; k < 11; k++) m.quad(rings[i][k], rings[i][k + 1], rings[i + 1][k + 1], rings[i + 1][k], SEG[k]);
    const a = [X[i], B[i], deckZ(X[i])], b = [X[i], -B[i], deckZ(X[i])];
    const c = [X[i + 1], -B[i + 1], deckZ(X[i + 1])], d = [X[i + 1], B[i + 1], deckZ(X[i + 1])];
    m.quad(a, b, c, d, COL.teak);
  }
  const t = rings[0];                                  // transom
  for (let k = 1; k < 11; k++) m.tri(t[0], t[k], t[k + 1], COL.hull);
  // cabin: slightly tapered box with dark windows
  const z0 = deckZ(0), z1 = z0 + 0.75;
  m.ref = [-0.4, 0, z0 + 0.35];
  m.hexa([[-2.4, -1.25, z0], [1.6, -1.1, z0], [1.6, 1.1, z0], [-2.4, 1.25, z0],
    [-2.2, -0.85, z1], [1.1, -0.8, z1], [1.1, 0.8, z1], [-2.2, 0.85, z1]], COL.cabin);
  for (const s of [1, -1]) {
    const w = (u, v) => {                              // point on the side face, u along, v up, pushed out a bit
      const x = lerp(-2.4, 1.6, u), xt = lerp(-2.2, 1.1, u), yb = lerp(1.25, 1.1, u), yt = lerp(0.85, 0.8, u);
      return [lerp(x, xt, v), s * (lerp(yb, yt, v) + 0.015), lerp(z0, z1, v)];
    };
    m.quad(w(0.12, 0.3), w(0.88, 0.3), w(0.88, 0.75), w(0.12, 0.75), COL.window);
  }
  m.ref = [-4, 0, -2];                                 // cockpit sole patch, faces up
  m.quad([-5.3, -1, deckZ(-5.3) + 0.02], [-2.6, -1, deckZ(-2.6) + 0.02], [-2.6, 1, deckZ(-2.6) + 0.02], [-5.3, 1, deckZ(-5.3) + 0.02], COL.cockpit);
  m.ref = [MAST_X, 0, 8];                              // mast
  m.box(MAST_X - 0.1, MAST_X + 0.1, -0.06, 0.06, z1 - 0.3, MAST_TOP, COL.spar);
  m.ref = [0, 0, -1.2];                                // keel fin + bulb
  m.box(-0.5, 1.0, -0.06, 0.06, -1.7, -0.3, COL.keel);
  m.ellipsoid(0.3, 0, -1.9, 1.0, 0.24, 0.24, COL.keel);
  return m;
}
function buildRudder() {      // local origin = rudder stock axis at the waterline plane
  const m = new MeshBuilder();
  m.ref = [-0.3, 0, -0.9];
  m.box(-0.62, 0.05, -0.04, 0.04, -1.45, -0.3, COL.rudder);
  return m;
}
function buildBoom() {        // pivots around the mast axis; local origin at the mast
  const m = new MeshBuilder();
  m.ref = [-2, 0, BOOM_Z];
  m.box(-4.4, 0, -0.05, 0.05, BOOM_Z - 0.06, BOOM_Z + 0.06, COL.spar);
  return m;
}
function buildMainsail() {
  const m = new MeshBuilder();
  m.quad([0, 0, BOOM_Z + 0.08], [-4.2, 0, BOOM_Z + 0.08], [-1.9, 0, 10.5], [-0.05, 0, MAST_TOP - 0.4], COL.sail);
  return m;
}
function buildJib() {
  const m = new MeshBuilder();
  m.tri(TACK, JIB_HEAD, JIB_CLEW, COL.jib);
  return m;
}

// ------------------------------------------------------------------ shaders
const SKY_VS = `attribute vec2 a_p; varying vec2 v_p; void main(){ v_p = a_p; gl_Position = vec4(a_p, 0.9999, 1.0); }`;
const SKY_FS = `precision mediump float;
varying vec2 v_p; uniform vec3 u_r, u_u, u_f; uniform vec2 u_t;
void main(){
  vec3 d = normalize(u_f + v_p.x*u_t.x*u_r + v_p.y*u_t.y*u_u);
  float h = clamp(d.y, 0.0, 1.0);
  vec3 c = mix(vec3(0.72,0.82,0.90), vec3(0.22,0.46,0.78), pow(h, 0.55));
  gl_FragColor = vec4(c, 1.0);
}`;
const BOAT_VS = `attribute vec3 a_pos; attribute vec3 a_nrm; attribute vec4 a_col;
uniform mat4 u_vp, u_model; varying vec3 v_n; varying vec4 v_c; varying vec3 v_w;
void main(){ vec4 w = u_model*vec4(a_pos,1.0); v_w = w.xyz; v_n = (u_model*vec4(a_nrm,0.0)).xyz; v_c = a_col; gl_Position = u_vp*w; }`;
const BOAT_FS = `precision mediump float;
varying vec3 v_n; varying vec4 v_c; varying vec3 v_w; uniform vec3 u_light;
void main(){
  vec3 n = normalize(v_n);
  float d = dot(n, u_light);
  float lit = v_c.a > 0.5 ? max(d, 0.0) + 0.15*max(-d, 0.0) : 0.55 + 0.45*abs(d);
  vec3 c = v_c.rgb * (0.38 + 0.7*lit);
  float fog = smoothstep(40.0, 90.0, length(v_w.xz));
  gl_FragColor = vec4(mix(c, vec3(0.72,0.82,0.90), fog), 1.0);
}`;
const SEA_VS = `attribute vec2 a_xy; uniform mat4 u_vp;
uniform float u_A, u_k, u_f, u_irr, u_p1, u_p2; uniform vec2 u_d;
varying vec3 v_pos; varying vec3 v_n;
void main(){
  float kr = u_k*dot(u_d, a_xy);
  float a1 = u_p1 - kr, a2 = u_p2 - u_f*kr;
  float eta = u_A*(cos(a1) + (u_irr/u_f)*cos(a2));
  vec2 g = (u_A*u_k*(sin(a1) + u_irr*sin(a2))) * u_d;
  v_n = normalize(vec3(-g.x, 1.0, -g.y));
  v_pos = vec3(a_xy.x, eta, a_xy.y);
  gl_Position = u_vp*vec4(v_pos, 1.0);
}`;
const SEA_FS = `precision mediump float;
varying vec3 v_pos; varying vec3 v_n; uniform vec3 u_eye;
void main(){
  vec3 N = normalize(v_n), V = normalize(u_eye - v_pos), L = normalize(vec3(0.35,0.8,0.45));
  float lam = max(dot(N, L), 0.0);
  vec3 col = mix(vec3(0.03,0.17,0.30), vec3(0.09,0.40,0.52), lam);
  float fres = pow(1.0 - max(dot(N, V), 0.0), 4.0);
  col = mix(col, vec3(0.62,0.76,0.88), fres*0.7);
  col += 0.45*pow(max(dot(reflect(-L, N), V), 0.0), 70.0);
  float fog = smoothstep(26.0, 58.0, length(v_pos.xz));
  col = mix(col, vec3(0.72,0.82,0.90), fog);
  gl_FragColor = vec4(col, mix(0.8, 1.0, fog));
}`;

function compile(gl, vs, fs) {
  const sh = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || 'shader error');
    return s;
  };
  const p = gl.createProgram(), v = sh(gl.VERTEX_SHADER, vs), f = sh(gl.FRAGMENT_SHADER, fs);
  gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p);
  gl.deleteShader(v); gl.deleteShader(f);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'link error');
  const u = {};
  const nU = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < nU; i++) { const n = gl.getActiveUniform(p, i).name; u[n] = gl.getUniformLocation(p, n); }
  return { p, u };
}

// ------------------------------------------------------------------ motion sample handling
const WAVE_KEYS = ['height', 'length', 'period', 'mu', 'irregularity', 'secondary', 'phase'];
const POSE_KEYS = ['roll', 'pitch', 'heel', 'yaw_wave', 'rudder'];

function angDiff(a, b) { return ((b - a + Math.PI * 3) % TAU) - Math.PI; }

function blend(a, b, u) {
  const o = { motoring: b.motoring, wave: {} };
  for (const k of POSE_KEYS) o[k] = lerp(a[k], b[k], u);
  o.awa = a.awa + angDiff(a.awa, b.awa) * u;
  for (const k of WAVE_KEYS) o.wave[k] = lerp(a.wave[k], b.wave[k], u);
  return o;
}

const REST = { roll: 0, pitch: 0, heel: 0, yaw_wave: 0, rudder: 0, awa: -0.6, motoring: false,
  wave: { height: 0, length: 39, period: 5, mu: 0.7, irregularity: 0, secondary: 1.6, phase: 0 } };

/** Sheet angle (deg) of the main as a function of |apparent wind angle| (deg). */
function sheetDeg(a) {
  const t = [[0, 8], [30, 10], [90, 35], [180, 80]];
  for (let i = 1; i < t.length; i++) if (a <= t[i][0]) return lerp(t[i - 1][1], t[i][1], (a - t[i - 1][0]) / (t[i][0] - t[i - 1][0]));
  return 80;
}

// ------------------------------------------------------------------ widget
export function createBoat3D(container) {
  container.classList.add('boat3d');
  const canvas = document.createElement('canvas');
  canvas.className = 'boat3d-canvas';
  const hud = document.createElement('div');
  hud.className = 'boat3d-hud mono';
  const hint = document.createElement('div');
  hint.className = 'boat3d-hint small';
  hint.textContent = 'drag to orbit · wheel to zoom · double-click to reset';
  container.append(canvas, hud, hint);

  let gl = null;
  try { gl = canvas.getContext('webgl', { antialias: true, alpha: false }) || canvas.getContext('experimental-webgl', { antialias: true, alpha: false }); } catch { /* fall through */ }
  if (!gl) {
    container.replaceChildren(Object.assign(document.createElement('div'), { className: 'boat3d-msg muted', textContent: '3D view unavailable (WebGL not supported).' }));
    return { update() {}, setActive() {}, destroy() {} };
  }

  let sky, boatProg, seaProg;
  try {
    sky = compile(gl, SKY_VS, SKY_FS); boatProg = compile(gl, BOAT_VS, BOAT_FS); seaProg = compile(gl, SEA_VS, SEA_FS);
  } catch (e) {
    container.replaceChildren(Object.assign(document.createElement('div'), { className: 'boat3d-msg muted', textContent: '3D view unavailable (' + e.message + ').' }));
    return { update() {}, setActive() {}, destroy() {} };
  }

  // geometry buffers
  const hull = buildHull().upload(gl), rudderM = buildRudder().upload(gl), boomM = buildBoom().upload(gl);
  const mainM = buildMainsail().upload(gl), jibM = buildJib().upload(gl);
  const skyBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, skyBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const seaVerts = new Float32Array((SEA_SEGS + 1) ** 2 * 2), seaIdx = new Uint16Array(SEA_SEGS * SEA_SEGS * 6);
  for (let j = 0, n = 0; j <= SEA_SEGS; j++) for (let i = 0; i <= SEA_SEGS; i++) {
    seaVerts[n++] = ((i / SEA_SEGS) * 2 - 1) * SEA_HALF; seaVerts[n++] = ((j / SEA_SEGS) * 2 - 1) * SEA_HALF;
  }
  for (let j = 0, n = 0; j < SEA_SEGS; j++) for (let i = 0; i < SEA_SEGS; i++) {
    const a = j * (SEA_SEGS + 1) + i, b = a + 1, c = a + SEA_SEGS + 1, d = c + 1;
    seaIdx.set([a, c, b, b, c, d], n); n += 6;
  }
  const seaBuf = gl.createBuffer(), seaIdxBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, seaBuf); gl.bufferData(gl.ARRAY_BUFFER, seaVerts, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, seaIdxBuf); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, seaIdx, gl.STATIC_DRAW);

  // jib rotation axis (forestay) and the sign that swings the clew to port (-Z in GL)
  const jibPivot = P(TACK), jibAxis = norm3(sub3(P(JIB_HEAD), jibPivot));
  const probe = M.about(M.axisAngle(jibAxis, 0.3), jibPivot), cg = P(JIB_CLEW);
  const jibSign = probe[2] * cg[0] + probe[6] * cg[1] + probe[10] * cg[2] + probe[14] > cg[2] ? -1 : 1; // want z' < z for +angle => port

  // ---- state
  let active = true, raf = 0, destroyed = false, lastHud = 0;
  let samples = [], phaseOff = 0, lastRawPhase = null;
  const cam = { az: 135 * D2R, el: 20 * D2R, dist: 38 };
  const camDefault = { ...cam };
  let width = 0, height = 0;

  function update(m) {
    if (!m || m.valid === false || !m.wave || typeof m.wave !== 'object') return;   // hold last pose
    const s = { t: performance.now(), motoring: !!m.motoring, awa: num(m.awa, REST.awa), wave: {} };
    for (const k of POSE_KEYS) s[k] = num(m[k]);
    for (const k of WAVE_KEYS) s.wave[k] = num(m.wave[k], REST.wave[k]);
    if (!(s.wave.secondary > 0)) s.wave.secondary = 1.6;
    if (!(s.wave.length > 0)) s.wave.length = 39;
    const raw = s.wave.phase;                          // unwrap cumulative phase (wraps at 2*pi*1000)
    if (lastRawPhase !== null && raw < lastRawPhase - PHASE_WRAP / 2) phaseOff += PHASE_WRAP;
    lastRawPhase = raw; s.wave.phase = raw + phaseOff;
    samples.push(s);
    if (samples.length > 6) samples.shift();
  }

  function currentPose(now) {
    const n = samples.length;
    if (n === 0) return REST;
    if (n === 1) return samples[0];
    const rt = now - RENDER_DELAY_MS;
    let a = samples[n - 2], b = samples[n - 1];
    for (let i = n - 1; i > 0; i--) if (samples[i - 1].t <= rt) { a = samples[i - 1]; b = samples[i]; break; }
    const span = b.t - a.t || 1;
    return blend(a, b, clamp((rt - a.t) / span, 0, 1.5));
  }

  // ---- camera
  let drag = null;
  const onDown = (e) => { drag = { id: e.pointerId, x: e.clientX, y: e.clientY }; try { canvas.setPointerCapture(e.pointerId); } catch { /* ignore */ } };
  const onMove = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    cam.az -= (e.clientX - drag.x) * 0.006;
    cam.el = clamp(cam.el + (e.clientY - drag.y) * 0.005, 3 * D2R, 85 * D2R);
    drag.x = e.clientX; drag.y = e.clientY;
  };
  const onUp = (e) => { if (drag && e.pointerId === drag.id) drag = null; };
  const onWheel = (e) => { e.preventDefault(); cam.dist = clamp(cam.dist * Math.exp(e.deltaY * 0.001), 10, 55); };
  const onDbl = () => Object.assign(cam, camDefault);
  canvas.style.touchAction = 'none';
  canvas.addEventListener('pointerdown', onDown); canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', onUp); canvas.addEventListener('pointercancel', onUp);
  canvas.addEventListener('wheel', onWheel, { passive: false }); canvas.addEventListener('dblclick', onDbl);
  const onLost = (e) => e.preventDefault();
  canvas.addEventListener('webglcontextlost', onLost);

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    width = Math.max(0, Math.round(container.clientWidth * dpr)); height = Math.max(0, Math.round(container.clientHeight * dpr));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
  if (ro) ro.observe(container);
  resize();

  // ---- drawing
  function bindMesh(prog, mesh) {
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buf);
    const bind = (name, size, off) => {
      const loc = gl.getAttribLocation(prog.p, name);
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 40, off * 4);
    };
    bind('a_pos', 3, 0); bind('a_nrm', 3, 3); bind('a_col', 4, 6);
  }
  const drawPart = (mesh, model) => {
    gl.uniformMatrix4fv(boatProg.u.u_model, false, model);
    bindMesh(boatProg, mesh);
    gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
  };

  function waveAt0(w) {            // eta at the boat origin (spec formula, r = 0)
    const A = w.height / 2, f = w.secondary;
    return A * (Math.cos(w.phase) + (w.irregularity / f) * Math.cos(f * w.phase + 0.7));
  }

  function render(now) {
    if (width === 0 || height === 0 || gl.isContextLost()) return;
    const p = currentPose(now), w = p.wave;
    gl.viewport(0, 0, width, height);
    gl.clearColor(0.72, 0.82, 0.9, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    const aspect = width / height, fovy = 40 * D2R;
    const eye = [cam.dist * Math.cos(cam.el) * Math.cos(cam.az), CAM_TARGET_Y + cam.dist * Math.sin(cam.el), cam.dist * Math.cos(cam.el) * Math.sin(cam.az)];
    const { view, right, up, fwd } = M.lookAt(eye, [0, CAM_TARGET_Y, 0]);
    const vp = M.mul(M.perspective(fovy, aspect, 0.5, 400), view);

    // sky
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND);
    gl.useProgram(sky.p);
    gl.uniform3fv(sky.u.u_r, right); gl.uniform3fv(sky.u.u_u, up); gl.uniform3fv(sky.u.u_f, fwd);
    gl.uniform2f(sky.u.u_t, Math.tan(fovy / 2) * aspect, Math.tan(fovy / 2));
    gl.bindBuffer(gl.ARRAY_BUFFER, skyBuf);
    const sl = gl.getAttribLocation(sky.p, 'a_p');
    gl.enableVertexAttribArray(sl); gl.vertexAttribPointer(sl, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disableVertexAttribArray(sl);

    // boat (opaque)
    gl.enable(gl.DEPTH_TEST);
    const heave = waveAt0(w);
    const boatM = M.mul(M.translate(0, heave, 0), M.mul(M.rotY(-p.yaw_wave), M.mul(M.rotZ(p.pitch), M.rotX(p.roll))));
    gl.useProgram(boatProg.p);
    gl.uniformMatrix4fv(boatProg.u.u_vp, false, vp);
    gl.uniform3fv(boatProg.u.u_light, norm3([0.35, 0.8, 0.45]));
    drawPart(hull, boatM);
    drawPart(rudderM, M.mul(boatM, M.mul(M.translate(RUDDER_X, 0, 0), M.rotY(p.rudder))));
    const sheet = p.motoring ? 0 : sheetDeg(Math.abs(p.awa) / D2R) * D2R;
    const side = p.awa >= 0 ? -1 : 1;                  // wind from starboard (awa > 0): sails to port (-Z)
    drawPart(boomM, M.mul(boatM, M.mul(M.translate(MAST_X, 0, 0), M.rotY(side * sheet))));
    if (!p.motoring) {
      const swing = M.mul(M.translate(MAST_X, 0, 0), M.rotY(side * sheet));
      drawPart(mainM, M.mul(boatM, swing));
      drawPart(jibM, M.mul(boatM, M.about(M.axisAngle(jibAxis, jibSign * -side * sheet * 0.85), jibPivot)));
    }
    for (const l of ['a_pos', 'a_nrm', 'a_col']) gl.disableVertexAttribArray(gl.getAttribLocation(boatProg.p, l));

    // sea (translucent, drawn last)
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(seaProg.p);
    const k = TAU / Math.max(w.length, 0.1), f = w.secondary;
    gl.uniformMatrix4fv(seaProg.u.u_vp, false, vp);
    gl.uniform3fv(seaProg.u.u_eye, eye);
    gl.uniform1f(seaProg.u.u_A, w.height / 2); gl.uniform1f(seaProg.u.u_k, k); gl.uniform1f(seaProg.u.u_f, f);
    gl.uniform1f(seaProg.u.u_irr, w.irregularity);
    gl.uniform1f(seaProg.u.u_p1, ((w.phase % TAU) + TAU) % TAU);                 // reduced in double precision
    gl.uniform1f(seaProg.u.u_p2, ((((f * w.phase + 0.7) % TAU) + TAU) % TAU));
    gl.uniform2f(seaProg.u.u_d, -Math.cos(w.mu), -Math.sin(w.mu));
    gl.bindBuffer(gl.ARRAY_BUFFER, seaBuf); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, seaIdxBuf);
    const al = gl.getAttribLocation(seaProg.p, 'a_xy');
    gl.enableVertexAttribArray(al); gl.vertexAttribPointer(al, 2, gl.FLOAT, false, 0, 0);
    gl.drawElements(gl.TRIANGLES, seaIdx.length, gl.UNSIGNED_SHORT, 0);
    gl.disableVertexAttribArray(al);
    gl.disable(gl.BLEND);

    if (now - lastHud > 100) {
      lastHud = now;
      const d = (r) => (r / D2R).toFixed(1) + '°';
      hud.textContent = `Roll ${d(p.roll)} (heel ${d(p.heel)})  Pitch ${d(p.pitch)}  Heave ${heave.toFixed(2)} m\n` +
        `Waves ${w.height.toFixed(1)} m / ${w.period.toFixed(1)} s`;
    }
  }

  function frame(now) {
    raf = 0;
    if (!active || destroyed) return;
    render(now);
    raf = requestAnimationFrame(frame);
  }
  function setActive(on) {
    active = !!on;
    if (active && !raf && !destroyed) { resize(); raf = requestAnimationFrame(frame); }
    if (!active && raf) { cancelAnimationFrame(raf); raf = 0; }
  }

  function destroy() {
    destroyed = true; setActive(false);
    if (ro) ro.disconnect();
    canvas.removeEventListener('pointerdown', onDown); canvas.removeEventListener('pointermove', onMove);
    canvas.removeEventListener('pointerup', onUp); canvas.removeEventListener('pointercancel', onUp);
    canvas.removeEventListener('wheel', onWheel); canvas.removeEventListener('dblclick', onDbl);
    canvas.removeEventListener('webglcontextlost', onLost);
    for (const b of [hull, rudderM, boomM, mainM, jibM]) gl.deleteBuffer(b.buf);
    gl.deleteBuffer(skyBuf); gl.deleteBuffer(seaBuf); gl.deleteBuffer(seaIdxBuf);
    for (const pr of [sky, boatProg, seaProg]) gl.deleteProgram(pr.p);
    const ext = gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
    container.replaceChildren();
  }

  setActive(true);
  return { update, setActive, destroy };
}
