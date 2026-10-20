# Architecture

## Layered pipeline

Each tick flows strictly downwards. Every layer reads only the snapshot produced by the layer above
and is a **pure function** where possible, so it can be tested without timers or sockets.

```
┌───────────────┐  scenario + UI commands
│   control     │──────────────────────────────────────────────────────────┐
└──────┬────────┘                                                          │
       ▼                                                                   │
┌───────────────┐  EnvironmentState (truth: wind over ground, current, waves, time)
│ environment   │  wind.py · current.py · waves.py
└──────┬────────┘
       ▼
┌───────────────┐  VesselState (truth: position, heading, STW, velocity over ground,
│   vessel      │  heel, roll/pitch, rudder, ROT, engine)   polar.py · heel.py ·
└──────┬────────┘  autopilot.py · motion.py · attitude.py
       ▼
┌───────────────┐  SensorReadings (what devices measure: AWA/AWS, HDG, STW, SOG/COG, …)
│   sensors     │  pure functions of (Environment, Vessel, StaticData)
└──────┬────────┘
       ▼
┌───────────────┐  CalculatedValues (TWA/TWS/TWD, set & drift, VMG, dew point)
│ calculations  │  only from SensorReadings, like an instrument processor
└──────┬────────┘
       ▼        ◄── ALL overrides applied here, after calculation (transmit-only semantics)
┌───────────────┐  SignalSnapshot: flat dict name → value (SI) + metadata
│   signals     │  registry.py (catalogue in signals.md), overrides.py
└──────┬────────┘
       ├──────────────► web (WebSocket push, ~4 Hz)
       ▼
┌───────────────┐  per-PGN schedulers pick latest snapshot at their own interval
│   n2k         │  devices.py · pgns/*.py (encoders) · fastpacket.py · canid.py
└──────┬────────┘
       ▼  CanFrame(id, data, timestamp)
┌───────────────┐
│   formats     │  ydraw.py  (seam for actisense.py, seasmart.py, nmea0183 later)
└──────┬────────┘
       ▼  bytes
┌───────────────┐
│  transport    │  udp.py (broadcast/unicast, batching) · tcp.py (server, N clients) ·
└───────────────┘  recorder.py (file)
```

## Package layout

```
n2k-sim/
├── pyproject.toml
├── README.md
├── data/
│   ├── polars/mock_cruiser_40.pol      mock polar (tab-separated, see simulation.md)
│   ├── heel_table.json                 heel lookup by AWS × AWA
│   └── scenarios/default.json          default scenario
├── src/n2k_sim/
│   ├── __main__.py                     CLI: python -m n2k_sim [--config …]
│   ├── app.py                          wires everything, owns the asyncio loop
│   ├── config.py                       pydantic settings + scenario model, load/save
│   ├── clock.py                        sim time, pause, deterministic seed
│   ├── units.py                        conversions (kn↔m/s, deg↔rad, °C↔K, …)
│   ├── geo.py                          angle wrap, vector add, great-circle step
│   ├── environment/  wind.py current.py waves.py state.py
│   ├── vessel/       polar.py heel.py autopilot.py motion.py attitude.py engine.py state.py
│   ├── sensors/      readings.py (one function per device family)
│   ├── calc/         wind.py current.py performance.py meteo.py
│   ├── signals/      catalogue.py registry.py overrides.py
│   ├── n2k/          canid.py fastpacket.py devices.py scheduler.py
│   │   └── pgns/     one module per PGN group: nav.py wind.py env.py engine.py tanks.py system.py
│   ├── formats/      ydraw.py (Format protocol)
│   ├── transport/    udp.py tcp.py recorder.py (Transport protocol)
│   └── web/          api.py ws.py  static/ index.html app.js gauge.js style.css
└── tests/            mirrors src/n2k_sim
```

## Key interfaces

```python
# environment / vessel: stateful models advanced by dt
class Model(Protocol):
    def step(self, t: float, dt: float, inputs) -> State: ...

# sensors / calc: pure
def read_sensors(env: EnvironmentState, vessel: VesselState, static: StaticData) -> SensorReadings
def calculate(readings: SensorReadings) -> CalculatedValues

# signals
@dataclass(frozen=True)
class SignalDef:          # one entry of the catalogue (signals.md)
    name: str             # "aws", "twd", "engine1.rpm"
    unit: Unit            # SI unit; UI converts
    layer: Layer          # ENV | SENSOR | CALC | STATIC
    min: float; max: float
    description: str

class SignalRegistry:     # holds current values + override per signal
    def snapshot(self) -> Mapping[str, float | None]
    def set_override(self, name: str, value: float | None) -> None   # None = auto

# n2k
@dataclass(frozen=True)
class PgnSpec:
    pgn: int; priority: int; interval_s: float; device: str; fast_packet: bool
    encode: Callable[[Mapping[str, float | None], int], bytes]   # (signals, sid) -> payload

class Format(Protocol):   def frames_to_bytes(self, frames: list[CanFrame]) -> bytes
class Transport(Protocol):
    async def start(self) -> None; async def send(self, data: bytes) -> None
    async def stop(self) -> None; def status(self) -> TransportStatus
```

## Runtime model

- One asyncio event loop (uvicorn) hosts: the **sim task** (fixed `dt = 0.1 s`), the
  **N2K scheduler task** (wakes at the next due PGN, ~ms resolution), transport tasks and the web
  app. No threads.
- The sim task publishes an immutable `SignalSnapshot` each tick; consumers read the latest one
  (no queues, no backpressure problems). Encoders never see partial updates.
- UI commands (REST/WebSocket) mutate **config objects only** (scenario parameters, overrides,
  autopilot target). Models read config at the start of each tick → no locking needed.
- Sequence IDs (SID) are shared per device and incremented per "measurement cycle" so related
  PGNs (e.g. 129026 and 129025 from the GPS) carry the same SID, as real devices do.
- UDP output batches frames into datagrams of ≤ 1400 bytes or every 50 ms, whichever comes
  first (mirrors SH-wg behaviour). TCP writes frames as produced; slow clients are dropped when
  their buffer exceeds 1 MB.

## Configuration & persistence

- `config.py` defines a pydantic `Scenario` (environment, vessel, autopilot, static data, overrides,
  output settings). JSON save/load via UI and `--scenario file.json` on the CLI.
- Runtime settings (bind addresses, ports, seed) via CLI flags / environment variables.

## Testing strategy

| Layer | Test |
|---|---|
| geo / units | property tests: wrap angles, vector round trips |
| environment | mean/limits over long runs with fixed seed (TWD stays within ± amplitude, gusts ≤ max) |
| vessel | autopilot converges; polar interpolation exact at grid points |
| sensors / calc | apparent→true→apparent round trip; set/drift recovers the configured current |
| n2k encoders | golden payloads; decode with an independent Python decoder in tests |
| fast-packet | frame count, sequence counter, padding |
| format / transport | YD RAW line grammar; TCP multi-client; UDP datagram size |
| end-to-end | run 60 s simulated time headless, decode the stream, compare to signal snapshot |

## Extension seams

- New wire format → implement `Format` (Actisense NGT, SeaSmart, NMEA 0183 translator).
- New PGN → add an encoder + `PgnSpec` entry; signals already exist in the registry.
- Waypoint navigation → new `navigation/` model feeding XTE / 129283 / 129284.
