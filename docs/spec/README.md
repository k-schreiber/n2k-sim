# n2k-sim — Specification

`n2k-sim` is a Python application that simulates the NMEA 2000 (N2K) traffic of a modern sailing
yacht and streams it over the network in **Yacht Devices RAW (YD RAW)** format via UDP and TCP — the
same format and default ports as a Hat Labs SH-wg or Yacht Devices YDWG-02 gateway. A browser UI
monitors and controls the simulation.

Primary use: developing and testing NMEA Dashboard (and other marine apps such as qtVLM, Signal K or
OpenCPN with N2K support) at the desk, without a boat.

| Document | Contents |
|---|---|
| [requirements.md](requirements.md) | Goals, non-goals, functional & non-functional requirements, assumptions |
| [architecture.md](architecture.md) | Modules, data flow, tick loop, interfaces, directory layout |
| [signals.md](signals.md) | Catalogue of every simulated, sensed, calculated and static signal |
| [simulation.md](simulation.md) | Wind, current, waves, boat motion, autopilot, polar, heel and attitude models |
| [n2k-output.md](n2k-output.md) | PGN mapping, gateway source, rates, YD RAW encoding, transports |
| [pgn-reference.md](pgn-reference.md) | Byte-level encoding reference per PGN (extracted from decoders) |
| [web-ui.md](web-ui.md) | UI pages, controls, REST and WebSocket API |
| [open-questions.md](open-questions.md) | Decisions taken as assumptions and questions still open |

## Decisions so far

| Topic | Decision |
|---|---|
| Output format | YD RAW only (text, one CAN frame per line), over UDP broadcast and TCP server |
| Boat motion | Autopilot modes: hold heading, hold TWA, motoring; position advances |
| Stack | Python 3.11+, FastAPI + uvicorn (asyncio), WebSocket push, vanilla JS + SVG, no build step, no CDN |
| Location | `NMEA Dashboard/n2k-sim`, own git repository |
