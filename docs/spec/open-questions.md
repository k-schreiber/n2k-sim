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

## Assumptions to confirm

| # | Assumption | Alternative |
|---|---|---|
| A1 | "VSOP" = VDOP; also send PDOP/TDOP | something else? |
| A2 | Compass reports **magnetic** heading + variation | true heading |
| A5 | Several virtual devices with own source addresses | single source like a simple gateway |
| A6 | Real-time only; no time acceleration | add 2×/5×/10× time scale |
| A8 | Depth: slow random walk 12–35 m | fixed default |
| A9 | Engine data sent only while RPM > 0 | always sent |
| A10 | No leeway, no sensor noise | optional noise/leeway later |

## Deferred (after v1)

Waypoint navigation (XTE, 129283/129284), NMEA 0183 output on SH-wg-like ports, headless mode,
time acceleration. The architecture keeps seams for each.

## Open

| # | Question |
|---|---|
| Q4 | Which yacht should the mock polar resemble (size/type)? Default: 40 ft cruiser. |
