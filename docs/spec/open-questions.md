# Open Questions & Assumptions

## Decided

| # | Question | Decision |
|---|---|---|
| D1 | Output format | YD RAW over UDP + TCP |
| D2 | Boat motion | Autopilot modes heading / TWA / motor |
| D3 | Stack | FastAPI + vanilla JS, asyncio, no build step |
| D4 | Location | `NMEA Dashboard/n2k-sim`, own git repo |

## Assumptions to confirm

| # | Assumption | Alternative |
|---|---|---|
| A1 | "VSOP" = VDOP; also send PDOP/TDOP | something else? |
| A2 | Compass reports **magnetic** heading + variation | true heading |
| A3 | Sensor overrides propagate into calculations (override AWS → TWS changes) | override only the transmitted value |
| A4 | Encode per NMEA 2000 spec, even where NMEA Dashboard decodes differently (exposes its bugs) | add an "app-compatible" switch |
| A5 | Several virtual devices with own source addresses | single source like a simple gateway |
| A6 | Real-time only; no time acceleration | add 2×/5×/10× time scale |
| A7 | Web UI on `127.0.0.1` only; data ports on all interfaces | UI on LAN too (e.g. control from a tablet) |
| A8 | Depth: slow random walk 12–35 m | fixed default |
| A9 | Engine data sent only while RPM > 0 | always sent |
| A10 | No leeway, no sensor noise | optional noise/leeway later |

## Open

| # | Question |
|---|---|
| Q1 | Should v1 include waypoint navigation (XTE, bearing/range to waypoint, 129283/129284)? |
| Q2 | Should a later version add NMEA 0183 output on SH-wg-like ports (2000/2222) for qtVLM testing? |
| Q3 | Is a headless mode (no web UI, scenario file only) needed, e.g. for CI tests of the dashboard? |
| Q4 | Which yacht should the mock polar resemble (size/type)? Default: 40 ft cruiser. |
