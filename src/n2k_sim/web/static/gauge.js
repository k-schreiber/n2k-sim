// SVG wind gauge and compass rose. No dependencies.
const NS = 'http://www.w3.org/2000/svg';
const rad = (a) => (a * Math.PI) / 180;
const pt = (r, a) => [r * Math.sin(rad(a)), -r * Math.cos(rad(a))];

function s(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  if (parent) parent.append(e);
  return e;
}
function div(cls, html) {
  const d = document.createElement('div');
  d.className = cls;
  if (html) d.innerHTML = html;
  return d;
}

/** Annular sector between radii r0<r1 from angle a0 to a1 (deg, clockwise from top). */
function sector(r0, r1, a0, a1) {
  const [x0, y0] = pt(r1, a0), [x1, y1] = pt(r1, a1), [x2, y2] = pt(r0, a1), [x3, y3] = pt(r0, a0);
  const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
  const sw = a1 > a0 ? 1 : 0;
  return `M${x0} ${y0}A${r1} ${r1} 0 ${large} ${sw} ${x1} ${y1}L${x2} ${y2}A${r0} ${r0} 0 ${large} ${1 - sw} ${x3} ${y3}Z`;
}

const BOAT = 'M0,-48C10,-35 16,-10 15,15C14,32 10,42 8,46L-8,46C-10,42 -14,32 -15,15C-16,-10 -10,-35 0,-48Z';
const CLOSE_HAULED = [30, 50]; // red/green sectors, degrees off the bow

function arrow(parent, len, color, width, headFrom = 0) {
  // arrow pointing up (negative y), from y=headFrom to y=-len
  const g = s('g', {}, parent);
  s('line', { x1: 0, y1: headFrom, x2: 0, y2: -len + 8, stroke: color, 'stroke-width': width, 'stroke-linecap': 'round' }, g);
  const head = s('path', { d: 'M0,-8L-6,6L6,6Z', fill: color }, g);
  head.setAttribute('transform', `translate(0 ${-len + 8})`);
  return g;
}

export function createWindGauge(host) {
  const svg = s('svg', { viewBox: '-165 -165 330 330', class: 'gauge', role: 'img', 'aria-label': 'Wind gauge' });
  s('circle', { r: 158, class: 'g-bg' }, svg);
  s('circle', { r: 140, class: 'g-ring' }, svg);
  s('path', { d: sector(126, 140, -CLOSE_HAULED[1], -CLOSE_HAULED[0]), class: 'g-port' }, svg);
  s('path', { d: sector(126, 140, CLOSE_HAULED[0], CLOSE_HAULED[1]), class: 'g-stbd' }, svg);
  for (let a = -180; a < 180; a += 10) {
    const major = a % 30 === 0;
    const [x0, y0] = pt(140, a), [x1, y1] = pt(major ? 126 : 132, a);
    s('line', { x1: x0, y1: y0, x2: x1, y2: y1, class: major ? 'g-tick major' : 'g-tick' }, svg);
    if (major) {
      const [tx, ty] = pt(112, a);
      const t = s('text', { x: tx, y: ty, class: 'g-lbl', 'text-anchor': 'middle', 'dominant-baseline': 'central' }, svg);
      t.textContent = String(Math.abs(a));
    }
  }
  s('path', { d: BOAT, class: 'g-boat' }, svg);
  s('line', { x1: 0, y1: -48, x2: 0, y2: -140, class: 'g-bow' }, svg);
  const twa = arrow(svg, 96, 'var(--twa)', 3);
  const awa = arrow(svg, 126, 'var(--awa)', 4);
  s('circle', { r: 5, class: 'g-hub' }, svg);

  const r = {};
  const ro = div('readouts');
  const mk = (id, lab, cls) => {
    const c = div('ro ' + cls);
    c.append(Object.assign(document.createElement('span'), { className: 'k', textContent: lab }));
    r[id] = Object.assign(document.createElement('span'), { className: 'v', textContent: '—' });
    c.append(r[id]);
    ro.append(c);
  };
  mk('aws', 'AWS kn', 'awa');
  mk('tws', 'TWS kn', 'twa');
  mk('twd', 'TWD °', 'twa');
  mk('awa', 'AWA °', 'awa');
  mk('twaV', 'TWA °', 'twa');
  host.append(svg, ro);

  const f = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d));
  return {
    update({ awa: a, twa: t, aws, tws, twd }) {
      awa.style.visibility = a == null ? 'hidden' : 'visible';
      twa.style.visibility = t == null ? 'hidden' : 'visible';
      if (a != null) awa.setAttribute('transform', `rotate(${a})`);
      if (t != null) twa.setAttribute('transform', `rotate(${t})`);
      r.aws.textContent = f(aws);
      r.tws.textContent = f(tws);
      r.twd.textContent = f(twd, 0);
      r.awa.textContent = f(a, 0);
      r.twaV.textContent = f(t, 0);
    },
  };
}

export function createCompass(host) {
  const svg = s('svg', { viewBox: '-165 -165 330 330', class: 'gauge', role: 'img', 'aria-label': 'Compass' });
  s('circle', { r: 158, class: 'g-bg' }, svg);
  const card = s('g', {}, svg);
  s('circle', { r: 140, class: 'g-ring' }, card);
  const names = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
  for (let a = 0; a < 360; a += 5) {
    const major = a % 30 === 0;
    const [x0, y0] = pt(140, a), [x1, y1] = pt(major ? 126 : a % 10 === 0 ? 132 : 135, a);
    s('line', { x1: x0, y1: y0, x2: x1, y2: y1, class: major ? 'g-tick major' : 'g-tick' }, card);
    if (major) {
      const [tx, ty] = pt(112, a);
      const t = s('text', { x: tx, y: ty, class: 'g-lbl' + (names[a] ? ' card-n' : ''), 'text-anchor': 'middle', 'dominant-baseline': 'central', transform: `rotate(${a} ${tx} ${ty})` }, card);
      t.textContent = names[a] || String(a);
    }
  }
  // wave arrow: sits on the inner ring at the direction the waves come from, pointing to the centre
  const waveG = s('g', {}, card);
  const wv = s('g', { class: 'wave' }, waveG);
  s('line', { x1: 0, y1: -100, x2: 0, y2: -70, stroke: 'var(--wave)', 'stroke-width': 4, 'stroke-linecap': 'round' }, wv);
  s('path', { d: 'M0,-60L-8,-76L8,-76Z', fill: 'var(--wave)' }, wv);
  const curG = s('g', {}, card);
  const cogG = s('g', {}, card);
  s('path', { d: 'M0,-140L-8,-155L8,-155Z', fill: 'var(--cog)' }, cogG);
  s('line', { x1: 0, y1: -140, x2: 0, y2: -126, stroke: 'var(--cog)', 'stroke-width': 2 }, cogG);
  s('path', { d: BOAT, class: 'g-boat', transform: 'scale(0.55)' }, svg);
  // fixed lubber line
  s('path', { d: 'M0,-138L-9,-158L9,-158Z', class: 'g-lubber' }, svg);

  let curArrow = null;
  const ro = div('readouts');
  const r = {};
  const mk = (id, lab, cls) => {
    const c = div('ro ' + cls);
    c.append(Object.assign(document.createElement('span'), { className: 'k', textContent: lab }));
    r[id] = Object.assign(document.createElement('span'), { className: 'v', textContent: '—' });
    c.append(r[id]);
    ro.append(c);
  };
  mk('hdg', 'HDG °', 'hdg');
  mk('cog', 'COG °', 'cog');
  mk('cur', 'Current ° / kn', 'cur');
  mk('wave', 'Waves ° / m', 'wave');
  host.append(svg, ro);

  const f = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d));
  return {
    update({ heading, cog, currentSet, currentDrift, waveDir, waveHeight }) {
      card.setAttribute('transform', `rotate(${-(heading || 0)})`);
      cogG.style.visibility = cog == null ? 'hidden' : 'visible';
      if (cog != null) cogG.setAttribute('transform', `rotate(${cog})`);
      waveG.style.visibility = waveDir == null ? 'hidden' : 'visible';
      if (waveDir != null) waveG.setAttribute('transform', `rotate(${waveDir})`);
      if (curArrow) curArrow.remove();
      if (currentSet != null) {
        const len = 28 + Math.min(currentDrift || 0, 3) * 24;
        curArrow = arrow(curG, len, 'var(--cur)', 4);
        curArrow.setAttribute('transform', `rotate(${currentSet})`);
      }
      r.hdg.textContent = f(heading, 0);
      r.cog.textContent = f(cog, 0);
      r.cur.textContent = `${f(currentSet, 0)} / ${f(currentDrift, 1)}`;
      r.wave.textContent = `${f(waveDir, 0)} / ${f(waveHeight, 1)}`;
    },
  };
}
