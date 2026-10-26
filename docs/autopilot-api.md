# Autopilot API — headless operation

How to steer the simulated boat over HTTP without the web UI — from scripts, tests or other tools. All endpoints are JSON over HTTP on the web UI server,
default `http://127.0.0.1:8080` (change with `--ui-host` / `--ui-port`). There is no auth.
Responses to write calls are `{"ok": true}`; invalid input returns HTTP 400 with `{"detail": "..."}`.

The autopilot is HTTP-only: the simulator does not accept autopilot commands from NMEA 2000
messages on its UDP/TCP outputs.

## Conventions

- Angles in degrees. Headings are **true**, 0–360.
- **TWA is signed**: positive = wind from starboard (starboard tack), negative = wind from port
  (port tack). Range −180…180.
- TWA is measured against the **water wind** (wind relative to the current, signal `env.wwd`),
  not the ground wind.
- The boat turns at most `boat.max_turn_rate` (default 6°/s); a tack takes ~15 s. Changes are
  targets, not instant course changes — poll state to see the boat converge.

## Modes

| `mode` | Steers to | Target field |
|---|---|---|
| `heading` | fixed true heading | `heading` |
| `twa` | fixed signed TWA; heading follows wind shifts | `twa` |
| `motor` | fixed true heading, speed from engine | `heading`, `rpm` |

## Endpoints

### Read the autopilot settings

`GET /api/scenario` → the full scenario; the autopilot is under `autopilot`:

```json
{"autopilot": {"mode": "twa", "heading": 0.0, "twa": -45.0, "rpm": 2200.0}, "...": "..."}
```

### Set mode and/or target

`PATCH /api/scenario/autopilot` with any subset of `mode`, `heading`, `twa`, `rpm`:

```bash
curl -X PATCH http://127.0.0.1:8080/api/scenario/autopilot \
  -H 'Content-Type: application/json' -d '{"mode": "twa", "twa": -45}'
```

```bash
curl -X PATCH http://127.0.0.1:8080/api/scenario/autopilot \
  -H 'Content-Type: application/json' -d '{"mode": "heading", "heading": 270}'
```

```bash
curl -X PATCH http://127.0.0.1:8080/api/scenario/autopilot \
  -H 'Content-Type: application/json' -d '{"mode": "motor", "heading": 90, "rpm": 2500}'
```

Setting a new target turns the boat the **shortest way**. Changing the sign of `twa` this way
tacks or gybes, whichever is shorter — use the tack/gybe endpoints to choose explicitly.

### Nudge the target

`POST /api/autopilot/adjust` with `{"delta": <degrees>}`. Meaning depends on mode:

| Mode | `delta > 0` | `delta < 0` |
|---|---|---|
| `heading`, `motor` | turn to starboard (heading + delta) | turn to port |
| `twa` | widen \|TWA\| (bear away), same tack | narrow \|TWA\| (head up), same tack |

In TWA mode the result is clamped to 0…180° on the current tack; the sign never flips.

```bash
curl -X POST http://127.0.0.1:8080/api/autopilot/adjust \
  -H 'Content-Type: application/json' -d '{"delta": -5}'
```

### Tack / gybe

`POST /api/autopilot/tack` and `POST /api/autopilot/gybe` (no body). Both put the boat on the
**opposite tack with the same absolute TWA**:

- **tack** turns toward the wind, through 0° TWA (sweeps 2·|TWA|).
- **gybe** turns away from the wind, through 180° TWA (sweeps 360 − 2·|TWA|).

In `twa` mode the TWA sign flips; in `heading`/`motor` mode the heading is mirrored through the
water-wind direction. Both work from any course, e.g. a "tack" at TWA 150° turns ~300° through
the wind.

```bash
curl -X POST http://127.0.0.1:8080/api/autopilot/tack
```

### Observe the boat

`GET /api/state` → `{running, sim_time, utc, signals: [...], scenario, output}`. Each signal is
`{name, label, unit, value, ...}`. Useful names:

| Signal | Meaning |
|---|---|
| `boat.heading` | true heading, deg |
| `boat.stw` | speed through water, kn |
| `boat.target_stw` | polar target speed, kn |
| `boat.awa`, `boat.aws` | apparent wind angle (signed) / speed |
| `env.wwd`, `env.wws` | water wind direction / speed (TWA reference) |

Current TWA = `wrap180(env.wwd − boat.heading)`.

```bash
curl -s http://127.0.0.1:8080/api/state \
  | jq '.signals[] | select(.name|test("boat.heading|boat.stw|env.wwd")) | {name, value}'
```

## Recipes

- **Beat upwind on port tack:** `PATCH {"mode": "twa", "twa": -42}`.
- **Tack and confirm:** `POST /tack`, then poll `/api/state` every 1–2 s until
  `wrap180(env.wwd − boat.heading)` is within ~2° of the new target (~15–20 s).
- **Hold a compass course:** `PATCH {"mode": "heading", "heading": 135}`; fine-tune with
  `adjust`.
- Always read `scenario.autopilot.mode` before `adjust` — the same delta means different things
  per mode.

## Related

- Simulation control: `POST /api/sim/pause`, `/api/sim/resume`, `/api/sim/reset`.
- Full API table: [spec/web-ui.md](spec/web-ui.md); autopilot model: [spec/simulation.md](spec/simulation.md).
