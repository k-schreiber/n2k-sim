// Small DOM helpers and reusable input widgets.
import { api } from './api.js';

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'for') el.htmlFor = v;
    else if (k in el && k !== 'list') { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function fmt(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (typeof v !== 'number') return String(v);
  return v.toFixed(d);
}

export function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  const p = (n) => String(n).padStart(2, '0');
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
}

export function toast(msg, isErr = false) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: 'toast' + (isErr ? ' err' : ''), text: msg });
  box.append(t);
  setTimeout(() => t.remove(), isErr ? 6000 : 2500);
}

/** Run an API call, toast on failure. Returns true on success. */
export async function call(method, path, body, okMsg) {
  try {
    await api(method, path, body);
    if (okMsg) toast(okMsg);
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}

const HOLD_MS = 2000; // ignore incoming state for a field this long after the user touched it
const round4 = (v) => String(+Number(v).toFixed(4));
const focused = (...els) => els.some((e) => e && document.activeElement === e);

/** Slider + number input row. commit(value) is debounced. */
export function numField({ label, min, max, step = 1, unit = '', slider = true, commit, hint }) {
  const num = h('input', { type: 'number', class: 'num', min, max, step });
  const rng = slider && min !== undefined && max !== undefined
    ? h('input', { type: 'range', class: 'rng', min, max, step }) : null;
  let touched = 0;
  let timer = null;
  const fire = () => {
    clearTimeout(timer);
    const v = parseFloat(num.value);
    if (Number.isFinite(v)) commit(v);
  };
  const user = (src) => {
    touched = Date.now();
    if (rng) { if (src === rng) num.value = rng.value; else rng.value = num.value; }
    clearTimeout(timer);
    timer = setTimeout(fire, 300);
  };
  num.addEventListener('input', () => user(num));
  num.addEventListener('change', () => { touched = Date.now(); fire(); });
  if (rng) rng.addEventListener('input', () => user(rng));
  const el = h('div', { class: 'frow' + (rng ? '' : ' noslider'), title: hint || '' },
    h('label', { text: label }), rng, num, h('span', { class: 'unit', text: unit }));
  return {
    el, input: num,
    set(v, force = false) {
      if (v === null || v === undefined) return;
      if (!force && (focused(num, rng) || Date.now() - touched < HOLD_MS)) return;
      const s = round4(v);
      if (num.value !== s) num.value = s;
      if (rng) rng.value = v;
    },
  };
}

/** Text / number input with label. commit(value) on change. */
export function textField({ label, type = 'text', width, commit, step, min, max, unit = '' }) {
  const input = h('input', { type, class: 'txt', step, min, max, style: width ? `width:${width}` : '' });
  let touched = 0;
  input.addEventListener('input', () => { touched = Date.now(); });
  input.addEventListener('change', () => {
    touched = Date.now();
    if (type === 'number') {
      const v = parseFloat(input.value);
      if (Number.isFinite(v)) commit(v);
    } else commit(input.value);
  });
  const el = h('div', { class: 'frow noslider' }, h('label', { text: label }), input, h('span', { class: 'unit', text: unit }));
  return {
    el, input,
    set(v, force = false) {
      if (v === null || v === undefined) v = '';
      if (!force && (focused(input) || Date.now() - touched < HOLD_MS)) return;
      const s = typeof v === 'number' ? round4(v) : String(v);
      if (input.value !== s) input.value = s;
    },
  };
}

export function switchField({ label, commit, inline = false }) {
  const cb = h('input', { type: 'checkbox' });
  let touched = 0;
  cb.addEventListener('change', () => { touched = Date.now(); commit(cb.checked); });
  const lab = h('label', { class: 'switch' }, cb, h('span', { class: 'track' }), h('span', { class: 'swtext', text: label }));
  const el = inline ? lab : h('div', { class: 'frow noslider' }, lab);
  return {
    el, input: cb,
    set(v) {
      if (focused(cb) || Date.now() - touched < HOLD_MS) return;
      cb.checked = !!v;
    },
  };
}

export function selectField({ label, options, commit }) {
  const sel = h('select', { class: 'sel' }, options.map(([v, t]) => h('option', { value: v, text: t })));
  let touched = 0;
  sel.addEventListener('change', () => { touched = Date.now(); commit(sel.value); });
  return {
    el: h('div', { class: 'frow noslider' }, h('label', { text: label }), sel),
    input: sel,
    set(v) { if (v === undefined || v === null || focused(sel) || Date.now() - touched < HOLD_MS) return; sel.value = v; },
  };
}

/**
 * Card for one scenario section; defs: {key,label,min,max,step,unit} or {key,label,bool:true,header:true}.
 * Changes PATCH /api/scenario/{section}.
 */
export function sectionCard(title, section, defs, extra = []) {
  const fields = [];
  const patch = (key, v) => call('PATCH', `/api/scenario/${section}`, { [key]: v });
  const headerBits = [];
  const body = [];
  for (const d of defs) {
    if (d.bool) {
      const f = switchField({ label: d.label, inline: !!d.header, commit: (v) => patch(d.key, v) });
      fields.push([d.key, f]);
      (d.header ? headerBits : body).push(f.el);
    } else {
      const f = numField({ ...d, commit: (v) => patch(d.key, v) });
      fields.push([d.key, f]);
      body.push(f.el);
    }
  }
  const el = h('section', { class: 'card' },
    h('div', { class: 'card-h' }, h('h3', { text: title }), h('div', { class: 'spacer' }), headerBits),
    h('div', { class: 'card-b' }, body, extra));
  return {
    el, fields,
    update(scn) {
      const sec = scn && scn[section];
      if (!sec) return;
      for (const [k, f] of fields) f.set(sec[k]);
    },
  };
}

/** Canvas sparkline. draw(times, values) with times in seconds. */
export class Spark {
  constructor(canvas, { color = '#6cf', label = '', unit = '', dec = 1, wrap = false, minSpan = 1, window = 600 }) {
    Object.assign(this, { canvas, color, label, unit, dec, wrap, minSpan, window });
  }

  draw(ts, vs) {
    const c = this.canvas;
    const w = c.clientWidth, hgt = c.clientHeight;
    if (!w || !hgt) return;
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hgt * dpr)) {
      c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr);
    }
    const g = c.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hgt);
    const css = getComputedStyle(document.documentElement);
    const dim = css.getPropertyValue('--dim').trim() || '#889';
    const grid = css.getPropertyValue('--line').trim() || '#333';
    g.font = '11px system-ui, sans-serif';
    const top = 16, bot = 4;
    g.strokeStyle = grid; g.lineWidth = 1;
    for (let i = 0; i < 3; i++) {
      const y = Math.round(top + ((hgt - top - bot) * i) / 2) + 0.5;
      g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
    }
    g.fillStyle = dim;
    g.fillText(this.label, 2, 11);
    if (!vs.length) return;
    let lo = Math.min(...vs), hi = Math.max(...vs);
    if (hi - lo < this.minSpan) { const m = (hi + lo) / 2; lo = m - this.minSpan / 2; hi = m + this.minSpan / 2; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const t1 = ts[ts.length - 1], t0 = t1 - this.window;
    const X = (t) => ((t - t0) / this.window) * w;
    const Y = (v) => top + (1 - (v - lo) / (hi - lo)) * (hgt - top - bot);
    g.beginPath();
    vs.forEach((v, i) => (i ? g.lineTo(X(ts[i]), Y(v)) : g.moveTo(X(ts[i]), Y(v))));
    g.strokeStyle = this.color; g.lineWidth = 1.6; g.stroke();
    g.lineTo(X(t1), hgt - bot); g.lineTo(X(ts[0]), hgt - bot); g.closePath();
    g.globalAlpha = 0.12; g.fillStyle = this.color; g.fill(); g.globalAlpha = 1;
    const m = (v) => (this.wrap ? ((v % 360) + 360) % 360 : v);
    const cur = `${m(vs[vs.length - 1]).toFixed(this.dec)} ${this.unit}`;
    g.fillStyle = this.color; g.textAlign = 'right';
    g.fillText(cur, w - 2, 11);
    g.fillStyle = dim;
    g.fillText(m(hi).toFixed(this.dec), w - 2, top + 10);
    g.fillText(m(lo).toFixed(this.dec), w - 2, hgt - bot - 2);
    g.textAlign = 'left';
  }
}
