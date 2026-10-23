// fetch + WebSocket helpers.

export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (typeof body === 'string') {
      opts.headers['Content-Type'] = 'text/plain';
      opts.body = body;
    } else {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
  }
  const r = await fetch(path, opts);
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    let d = data && data.detail !== undefined ? data.detail : null;
    if (d && typeof d !== 'string') d = JSON.stringify(d);
    throw new Error(d || `${method} ${path}: HTTP ${r.status}`);
  }
  return data;
}

/** WebSocket with exponential backoff reconnect and a stale-connection watchdog. */
export class Socket {
  constructor({ onState, onRaw, onStatus, onMotion }) {
    this.onState = onState || (() => {});
    this.onRaw = onRaw || (() => {});
    this.onStatus = onStatus || (() => {});
    this.onMotion = onMotion || null;
    this.subs = new Set();
    this.attempt = 0;
    this.ws = null;
    this.lastMsg = 0;
    this.timer = null;
  }

  connect() {
    clearTimeout(this.timer);
    const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    let ws;
    try { ws = new WebSocket(url); } catch { this._retry(); return; }
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.lastMsg = Date.now();
      this.onStatus(true);
      for (const t of this.subs) this._send({ subscribe: t });
    };
    ws.onmessage = (ev) => {
      this.lastMsg = Date.now();
      let m;
      try { m = JSON.parse(ev.data); } catch { return; }
      if (m.type === 'state') this.onState(m);
      else if (m.type === 'raw') this.onRaw(m.lines || []);
      else if (m.type === 'motion' && this.onMotion) this.onMotion(m);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.onStatus(false);
      this._retry();
    };
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
    if (!this.watchdog) {
      this.watchdog = setInterval(() => {
        if (this.ws && this.ws.readyState === 1 && Date.now() - this.lastMsg > 6000) {
          try { this.ws.close(); } catch { /* ignore */ }
        }
      }, 2000);
    }
  }

  _retry() {
    const delay = Math.min(500 * Math.pow(1.7, this.attempt++), 10000);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.connect(), delay);
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(obj));
  }

  subscribe(topic) { this.subs.add(topic); this._send({ subscribe: topic }); }
  unsubscribe(topic) { this.subs.delete(topic); this._send({ unsubscribe: topic }); }
}
