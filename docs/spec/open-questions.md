# Open Questions & Assumptions

## Decided

| # | Question | Decision |
|---|---|---|
| D1 | Output format | YD RAW over UDP + TCP |
| D2 | Boat motion | Autopilot modes heading / TWA / motor |
| D3 | Stack | FastAPI + vanilla JS, asyncio, no build step |
| D4 | Location | `NMEA Dashboard/n2k-sim`, own git repo |
| D5 | Override semantics | Transmit-only: calculations use simulated values |
| D6 | Encoding vs. app quirks | Strictly per NMEA 2000 spec |
| D7 | Web UI access | `127.0.0.1` by default, `--ui-host` flag to open it up |
| D8 | v1 scope | Core only; waypoints, 0183 output, headless mode, time acceleration deferred |
| D9 | GNSS data | VDOP plus all usual GPS data (fix, satellites, DOPs, altitude, time) |
| D10 | Compass | Industry-standard fluxgate: magnetic heading, variation from GPS |
| D11 | Network | Single gateway source, modular sensors in code |
| D12 | Time | Real time only |
| D13 | Depth | Slow random walk 12–35 m |
| D14 | Engine | Data only while RPM > 0 |
| D15 | Noise / leeway | No noise; leeway modelled in the boat tier |
| D16 | Pipeline | Three tiers: environment → boat → sensors |
| D17 | Mock polar | 40 ft cruiser |

## Deferred (after v1)

Waypoint navigation (XTE, 129283/129284), NMEA 0183 output on SH-wg-like ports, headless mode,
time acceleration. The architecture keeps seams for each.

## Open

None at the moment.
