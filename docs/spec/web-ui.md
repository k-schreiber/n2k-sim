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

### 3. Vessel
Autopilot mode and targets, polar (select file / upload .pol, preview table and polar diagram),
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

## API

REST (JSON, SI units are **not** used here — the API speaks UI units with explicit unit keys so
the frontend stays dumb; conversion lives in `units.py`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | full snapshot (signals, env, vessel, output status) |
| GET/PUT | `/api/scenario` | read / replace whole scenario |
| PATCH | `/api/env/{wind,current,waves,depth}` | change parameters / fixed flag |
| POST | `/api/env/wind/gust` | trigger gust |
| PATCH | `/api/autopilot` | mode, targets; `POST /api/autopilot/{tack,gybe}` |
| PATCH | `/api/static/{group}` | static values |
| PUT/DELETE | `/api/signals/{name}/override` | set / clear override |
| GET/PUT | `/api/polar` | current polar table / upload |
| PATCH | `/api/output/{udp,tcp,recorder}` | transport settings |
| PATCH | `/api/output/pgns/{pgn}` | enable, interval |
| POST | `/api/sim/{pause,resume,reset}` | run control |

WebSocket `/ws`: server pushes `{"type":"state", …}` at 4 Hz and `{"type":"raw", "lines":[…]}`
(throttled, only while the Output view is open). Client sends nothing except view subscriptions;
all mutations use REST (simple, testable, curl-able).
