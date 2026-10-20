# Signal Catalogue

Every value the simulator handles is a named **signal** in the registry. Layers:
**ENV** = simulation truth (not sent directly), **SEN** = sensor reading, **CALC** = calculated from
sensor readings, **STAT** = static value set by the user. Every SEN/CALC/STAT signal can be
overridden with a fixed value; ENV parameters have their own auto/fixed switch (simulation.md).
Overrides are **transmit-only**: they replace the value in the outgoing PGNs and in the UI's
"sent" column, but calculations keep using the simulated value (the UI shows both).

## Environment truth (ENV — shown in UI, not transmitted)

| Signal | UI unit | Notes |
|---|---|---|
| `env.gwd`, `env.gws` | °T, kn | wind over ground (from) |
| `env.wwd`, `env.wws` | °T, kn | wind relative to water = ground wind − current |
| `env.current_set`, `env.current_drift` | °T, kn | |
| `env.wave_dir`, `env.wave_height`, `env.wave_length`, `env.wave_period` | °T, m, m, s | |
| `env.depth` | m | depth below waterline at boat position |

## Sensors (SEN)

| Signal | UI unit | Device (virtual) | PGN |
|---|---|---|---|
| `awa`, `aws` | °, kn | wind sensor | 130306 ref 2 |
| `heading_mag`, `deviation` | °M, ° | compass | 127250 |
| `heading_true` | °T | compass (derived with variation) | 127250 (if set to true) |
| `variation` | ° (E+) | compass / GPS | 127250, 127258 |
| `rot` | °/min | compass | 127251 |
| `yaw`, `pitch`, `roll` | ° | compass (attitude) | 127257 |
| `rudder` | ° (stbd +) | rudder sensor | 127245 |
| `stw` | kn | speed log | 128259 |
| `log_total`, `log_trip` | nm | speed log | 128275 |
| `water_temp` | °C | speed log / depth | 130312 (src 0), 130310 |
| `depth`, `depth_offset` | m | depth sounder | 128267 |
| `lat`, `lon` | ° | GPS | 129025, 129029 |
| `cog`, `sog` | °T, kn | GPS | 129026 |
| `gnss_time` | UTC | GPS | 126992, 129029, 129033 |
| `hdop`, `vdop`, `pdop`, `tdop`, `satellites`, `altitude` | –, m | GPS | 129029, 129539 |

## Calculated (CALC) — instrument processor

| Signal | UI unit | Formula (from sensor values only) | PGN |
|---|---|---|---|
| `tws`, `twa` | kn, ° | `x = AWS·sin AWA; y = AWS·cos AWA − STW; TWS = √(x²+y²); TWA = atan2(x, y)` | 130306 ref 3 |
| `twd` | °T | `heading_true + TWA` | 130306 ref 0 |
| `gws`, `gwd` | kn, °T | as TWS/TWD but with SOG/COG instead of STW/heading (ground wind) | – (UI) |
| `current_set`, `current_drift` | °T, kn | `C = V(SOG, COG) − V(STW, heading_true)` | 129291 |
| `vmg_wind` | kn | `STW · cos TWA` | – (UI) |
| `polar_speed`, `performance` | kn, % | polar(TWS, TWA); STW / polar_speed | – (UI) |
| `dew_point` | °C | Magnus formula from air temp and humidity | 130316 (src 9) |

Consistency property (no sensor errors, no leeway): calculated TWS/TWA/TWD equal the
environment's water-referenced wind `env.wws/wwd` exactly, and `current_set/drift` equal the
environment current. Unit tests assert this.

## Static (STAT)

| Group | Signals (default) | PGN |
|---|---|---|
| Meteo | `air_temp` (22 °C), `pressure` (1013.2 hPa), `humidity` (65 %), `cabin_temp` (24 °C) | 130310, 130311, 130312, 130313, 130314 |
| Engine 1 | `engine.rpm` (0 sailing / auto from motor mode), `engine.oil_pressure` (3.5 bar), `engine.coolant_temp` (80 °C), `engine.oil_temp` (90 °C), `engine.alternator_v` (14.2 V), `engine.fuel_rate` (2.5 L/h), `engine.hours` (1250 h), `engine.load` (40 %) | 127488, 127489 |
| Tanks | `tank.fuel` (75 % of 200 L), `tank.fresh_water1` (60 % of 300 L), `tank.fresh_water2` (90 % of 150 L), `tank.black_water` (20 % of 80 L) | 127505 |
| Batteries | `battery.house` (12.6 V, −4.2 A, 25 °C), `battery.engine` (12.8 V, 0 A, 22 °C) | 127508 |
| Config | `depth_offset` (−1.8 m keel), `variation` (+4.5° E), `deviation` (0°) | 128267, 127250, 127258 |

Engine values other than RPM are sent only while `engine.rpm > 0` (otherwise null/not sent,
matching a switched-off engine ECU); configurable.

## Not in v1 (candidates)

XTE, waypoint bearing/range (129283/129284) — needs a navigation model; AIS; autopilot status;
B&G performance PGNs (proprietary); AC/solar charger data.
