# Requirements

## Goals

1. Produce a **constant, realistic N2K stream** of a sailing yacht: the PGNs, rates, source
   addresses and fast-packet framing a real backbone carries.
2. Keep all values **mutually consistent** (e.g. apparent wind, true wind, heading, STW, SOG/COG
   and current always satisfy the vector relations) and **within plausible ranges**.
3. Let the user **observe and steer** the scenario from a browser: environment parameters,
   autopilot, static values, per-signal overrides.
4. Be **simple to run** (`pip install -e .` / `python -m n2k_sim`) and simple to extend
   (one module per concern, pure functions where possible, unit-testable without network).

## Non-goals

- Physically accurate hydrodynamics or aerodynamics; sensor noise, latency, calibration errors.
- A realistic multi-device N2K network (one gateway source instead).
- Writing to a real CAN bus (no CAN adapter support — avoids disturbing a real boat network).
- Receiving or acting on N2K input (the TCP server ignores anything clients send).
- AIS targets, autopilot commands, alarms, multi-boat scenarios (possible later extensions).
- Other wire formats (Actisense, SeaSmart, NMEA 0183) — architecture keeps a seam for them.

## Functional requirements

### FR-1 Simulation core
- FR-1.0 Three tiers, each depending only on the one above: (1) lean **environment** simulation,
  (2) very lean **boat** simulation, (3) noise-free **sensors**. See [architecture.md](architecture.md).
- FR-1.1 Fixed-step simulation tick (default 10 Hz) in real time; pause / resume; reset to scenario.
- FR-1.2 Environment: wind (TWD, TWS, oscillation, gusts), current (set, drift), waves (direction,
  height, period). See [simulation.md](simulation.md).
- FR-1.3 Boat: position, heading, STW from polar, heel from lookup, **leeway** from heel and STW,
  attitude from waves, rudder and rate of turn from the autopilot, engine for motoring.
- FR-1.4 Autopilot modes: `heading` (hold compass course), `twa` (hold true wind angle, tacks or
  gybes when the target changes sign), `motor` (hold heading, speed from engine RPM).
- FR-1.5 Every environment parameter can be **fixed** (oscillation/gusts disabled) from the UI.

### FR-2 Sensors, calculations, static data
- FR-2.1 Sensors are pure functions of the simulation state (no errors), producing the "raw" values
  devices on the bus would report: AWA, AWS, magnetic heading (fluxgate), ROT, attitude, rudder,
  STW, depth, water temperature, log/trip, and the usual GNSS data (position, altitude, COG, SOG,
  date/time, variation, fix type, satellites used/in view, HDOP/VDOP/PDOP/TDOP).
- FR-2.2 Calculated values derived **only from sensor values** (as instruments do): true heading, leeway
  (with editable correction factor), TWA, TWS, TWD, set & drift, VMG, dew point.
- FR-2.3 Static values set in the UI: air temperature, pressure, humidity, engine (RPM, oil
  pressure, coolant temp, alternator voltage, hours), tanks (fuel, fresh water, black water),
  batteries (voltage, current, temperature), depth transducer offset, magnetic variation.
- FR-2.4 **Overrides**: any sensor, calculated or static signal can be switched from `auto` to a
  fixed value. Overrides affect **only what is transmitted** (and shown as "sent" in the UI);
  calculations always use the simulated values, so overrides can create deliberately inconsistent
  data for testing.

### FR-3 N2K output
- FR-3.1 Encode the PGNs in [n2k-output.md](n2k-output.md) at realistic per-PGN intervals.
- FR-3.2 Fast-packet framing for PGNs longer than 8 bytes; correct sequence counters per PGN.
- FR-3.3 All PGNs are emitted by a single **gateway** source address with one ISO address claim
  (PGN 60928) at start and periodically. No simulated multi-device network; sensor modules stay
  separate in code so per-device addresses remain possible later.
- FR-3.4 YD RAW lines `hh:mm:ss.mmm R XXXXXXXX b0 b1 … b7\r\n`.
- FR-3.5 UDP broadcast (default port 2002, configurable target address incl. unicast) and TCP
  server (default port 2223, multiple clients). Each transport can be enabled independently.
- FR-3.6 Per-PGN enable/disable and interval override from the UI.
- FR-3.7 Optional recording of the output stream to a `.raw` file (replayable with existing tools).

### FR-4 Web UI
- FR-4.1 Live dashboard with a classic **wind gauge** (AWA/TWA needles, AWS/TWS readouts), heading,
  SOG/COG, STW, depth, heel.
- FR-4.2 Environment configuration (wind, current, waves) with auto/fixed switches.
- FR-4.3 Boat & autopilot control, polar file selection/upload.
- FR-4.4 Static data editor.
- FR-4.5 Signal table: every signal with current value, unit, source layer, override toggle.
- FR-4.6 Output monitor: transport status, client count, frames/s per PGN, tail of the YD RAW stream.
- FR-4.7 Save / load scenario (JSON).

## Non-functional requirements

- NFR-1 Python ≥ 3.11, dependencies limited to FastAPI, uvicorn, pydantic (+ pytest for dev).
- NFR-2 Single process, asyncio; CPU < 5 % on a laptop at default rates.
- NFR-3 Web UI binds to `127.0.0.1` by default; data ports bind `0.0.0.0` (needed for phones and
  emulators) — both configurable. No authentication (local tool), no remote assets.
- NFR-4 Deterministic mode: fixed random seed so tests and recordings are reproducible.
- NFR-5 Unit tests for models, calculations, encoders and framing; an end-to-end test decodes the
  stream back and checks values.
- NFR-6 Internal units SI (m, m/s, rad, K, Pa) — conversion only at the UI boundary and in encoders.

## Assumptions (educated guesses)

- "VSOP" means **VDOP**; the GPS reports all usual GNSS data (see signals.md). *(confirmed)*
- Heading comes from an industry-standard **fluxgate** compass: magnetic heading only; variation
  from the GPS in PGN 127258. *(confirmed)*
- Wind is defined **over ground** in the environment. Instruments calculate "true wind" from
  apparent wind, STW, heading and leeway (water-referenced), so with current present calculated
  TWS/TWD differ from the ground wind — realistic and intentional.
- Leeway is modelled in tier 2 (`λ = K·heel/STW²`); no sensor noise. *(confirmed)*
- Default start position: off Split, Croatia (43.48 N, 16.40 E) — editable.
