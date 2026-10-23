# Web UI

Single-page app served by FastAPI at `http://127.0.0.1:8080/`. Vanilla JS modules, SVG gauges,
one CSS file, dark theme by default (night-friendly), no external assets. Units in the UI: knots,
degrees, metres, °C, hPa, % (switchable later).

## Layout

Top bar: run state (▶ / ⏸ / reset), sim time, frames/s, TCP clients, scenario load/save.
Left navigation with six views:

### 1. Dashboard
- **Wind gauge** (SVG, classic close-hauled style): boat outline, 0–180° port/starboard scale with
  red/green sectors, AWA needle, TWA needle (different colour), digital AWS / TWS / TWD.
- Compass rose: heading, COG marker, current arrow, wave direction arrow.
- Tiles: STW, SOG, COG, depth, heel/pitch, rudder, VMG, polar %, engine RPM.
- Sparklines (last 10 min): TWD, TWS (with gusts visible), STW.
- Autopilot quick controls: mode, target, ±1/±10, Tack/Gybe.

### 2. Environment
Three cards — **Wind**, **Current**, **Waves** — each parameter from simulation.md with a slider +
number input, and per card a **Fixed / Simulated** switch. Wind card: "Gust now" button, live
mini-chart of TWD/TWS. Depth: range or fixed, "Shallow patch" button.

### 3. Boat
Autopilot mode and targets, leeway factors (boat K, instrument K), polar (select file / upload .pol, preview table and polar diagram),
heel table preview, engine-to-speed table, start position (lat/lon) and "teleport".

### 4. Static data
Forms per group (Meteo, Engine, Tanks, Batteries, Config) from signals.md.

### 5. Signals
Table of every SEN/CALC/STAT signal: name, simulated value, **sent** value (differs when
overridden), unit, layer, PGN(s), **override** toggle + value field. Filter by layer/group. Overridden rows highlighted.

### 6. Output
Transport cards (enable, address, port, status, bytes/s, clients), recorder toggle, PGN table
(enable, interval, frames/s, last payload hex), live tail of the YD RAW stream (last 200 lines,
pause, PGN filter).

## API (contract)

The API speaks **human units**: scenario fields as in `src/n2k_sim/config.py`, signal values in
each signal's UI unit (`units.UI_UNITS`). JSON everywhere.

### `GET /api/state` (also pushed on `/ws` as `{"type": "state", ...}` at 4 Hz)

```json
{
  "running": true,
  "sim_time": 123.4,
  "utc": 1760000000.0,
  "signals": [
    {"name": "aws", "label": "Apparent wind speed", "group": "wind", "layer": "sensor",
     "unit": "kn", "value": 14.2, "sent": 14.2, "overridden": false, "pgns": [130306]}
  ],
  "scenario": { "...": "full Scenario, see config.py" },
  "output": {
    "frames_per_s": 118.0,
    "udp": {"enabled": true, "host": "255.255.255.255", "port": 2002, "bytes_per_s": 5900, "error": null},
    "tcp": {"enabled": true, "host": "0.0.0.0", "port": 2223, "clients": 1, "bytes_per_s": 5900, "error": null},
    "recorder": {"enabled": false, "path": null},
    "pgns": [{"id": "130306.apparent", "pgn": 130306, "name": "Wind (apparent)", "enabled": true,
              "interval_s": 0.1, "frames_per_s": 10.0, "last_hex": "00 6A 01 ..."}]
  }
}
```

- `value` = simulated value, `sent` = value after override (null for env-layer signals).
- Non-scalar signals (`satellites`) are omitted from `signals`.
- `unit` is the display label (e.g. "kn", "°", "°C").

### Mutations

| Method | Path | Body | Purpose |
|---|---|---|---|
| PATCH | `/api/scenario/{section}` | partial object | sections: wind, current, waves, seabed, boat, autopilot, gps, processor |
| PATCH | `/api/static` | `{"engine.rpm": 1800, ...}` | static signal values (UI units) |
| PUT | `/api/overrides/{name}` | `{"value": 25}` | set override (UI units) |
| DELETE | `/api/overrides/{name}` | – | clear override |
| PATCH | `/api/output` | `{"udp": {...}, "tcp": {...}, "recorder": true, "source": 35}` | transports (partial) |
| PATCH | `/api/output/pgns/{id}` | `{"enabled": false, "interval_s": 0.5}` | per-PGN schedule |
| POST | `/api/wind/gust` | – | gust now |
| POST | `/api/seabed/shallow` | – | ramp depth to 3 m for 60 s |
| POST | `/api/autopilot/tack` · `/gybe` | – | flip TWA sign (twa mode) or mirror heading through the wind |
| POST | `/api/autopilot/adjust` | `{"delta": 10}` | change target heading / TWA by delta degrees |
| POST | `/api/log/reset_trip` | – | |
| POST | `/api/sim/pause` · `/resume` · `/reset` | – | run control; reset restarts from the current scenario |
| GET / PUT | `/api/scenario` | Scenario | download / load whole scenario |
| GET | `/api/polar` | – | `{"name": "...", "tws": [..kn], "twa": [..deg], "speed": [[..kn]]}` rows = twa |
| PUT | `/api/polar` | text/plain .pol | upload & activate polar |

All mutations return `{"ok": true}` or HTTP 400 with `{"detail": "..."}`.

### WebSocket `/ws`

Server → client: `{"type": "state", ...}` (4 Hz), `{"type": "raw", "lines": ["..."]}` (≤ 5 Hz,
only after the client subscribed), `{"type": "motion", ...}` (10 Hz, only after subscribing).
Client → server: `{"subscribe": "raw" | "motion"}` / `{"unsubscribe": "raw" | "motion"}`.

`motion` carries the boat's attitude and the sea state for the 3D view, in SI units (rad, m, m/s):

```json
{"type": "motion", "valid": true, "t": 123.4,
 "roll": 0.21, "pitch": -0.03, "heel": 0.19, "yaw_wave": 0.01, "heading": 4.4,
 "leeway": 0.07, "rudder": -0.05, "awa": -0.52, "aws": 8.1, "stw": 3.0, "motoring": false,
 "wave": {"height": 1.0, "length": 39.0, "period": 5.0, "mu": 0.6, "phase": 812.3,
          "irregularity": 0.2, "secondary": 1.6}}
```

Sea surface in boat coordinates (x forward, y starboard, z up), with `A = height/2`,
`k = 2π/length`, `f = secondary`, travel direction `d = (−cos mu, −sin mu)`:
`η(r) = A·[cos(phase − k·d·r) + (irregularity/f)·cos(f·phase + 0.7 − f·k·d·r)]`.
Wave roll and pitch are derived from the slope of this surface at the boat (simulation.md §6), so
a renderer that draws it sees the boat ride the waves consistently. Heave = `η(0)`.
