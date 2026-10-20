# Architecture

## Three simulation tiers + processing + output

The simulation is split into **three tiers**, each lean and each depending only on the tier
above. Everything after tier 3 is "the boat's electronics": instrument calculations, the gateway
and the network output. Each tick flows strictly downwards; tiers 1–2 are stateful models stepped
by `dt`, tier 3 and everything below are **pure functions** of their inputs, testable without
timers or sockets.

```
 scenario + UI commands ──► config (read by every tier at the start of a tick)

 ═══ TIER 1 · ENVIRONMENT (lean) ══════════════════════════════════════════════════
   EnvironmentState: wind over ground (TWD/TWS with oscillation & gusts), current,
   waves, depth under the boat, meteo            environment/ wind · current · waves · seabed
 ═══ TIER 2 · BOAT (very lean) ════════════════════════════════════════════════════
   BoatState: position, heading, course through water, STW, leeway, heel,
   roll/pitch/yaw, rudder, ROT, engine            boat/ polar · heel · leeway · autopilot ·
                                                        motion · attitude · engine
 ═══ TIER 3 · SENSORS (no noise) ══════════════════════════════════════════════════
   SensorReadings: what each device measures     sensors/ one module per device type:
   (pure functions of Environment + Boat +       gps · compass · wind_sensor · speed_log ·
    StaticData)                                   depth_sounder · rudder · engine · tanks ·
                                                  battery · weather
 ══════════════════════════════════════════════════════════════════════════════════
   ▼
 calc/         CalculatedValues: TWA/TWS/TWD, set & drift, VMG, dew point —
               only from SensorReadings, like an instrument processor
   ▼  ◄── overrides applied here (transmit-only: calculations above never see them)
 signals/      SignalSnapshot: flat dict name → value (SI) + metadata ─────► web/ (4 Hz push)
   ▼
 n2k/          gateway: per-PGN scheduler → encoders (pgns/*) → fast-packet → CAN frames,
               one source address (see n2k-output.md)
   ▼  CanFrame(id, data, timestamp)
 formats/      ydraw.py   (seam: actisense, seasmart, nmea0183)
   ▼  bytes
 transport/    udp.py · tcp.py · recorder.py
```

Why three tiers: the environment knows nothing about the boat, the boat knows nothing about
instruments, and sensors only *observe* — so e.g. adding leeway (tier 2) automatically changes
what the GPS reports (tier 3) and therefore what the instrument processor calculates, without any
special-casing.

**Device modularity without a simulated network:** each sensor module declares the signals it
produces and the PGNs that carry them (`DeviceSpec`). The gateway collects all enabled devices and
emits their PGNs from **one source address**, like a simple gateway or multiplexer would. Giving
devices their own addresses later only touches `n2k/gateway.py`.

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
│   ├── environment/  wind.py current.py waves.py seabed.py state.py        (tier 1)
│   ├── boat/         polar.py heel.py leeway.py autopilot.py motion.py
│   │                 attitude.py engine.py state.py                        (tier 2)
│   ├── sensors/      base.py (DeviceSpec) gps.py compass.py wind_sensor.py speed_log.py
│   │                 depth_sounder.py rudder.py engine.py tanks.py battery.py weather.py (tier 3)
│   ├── calc/         wind.py current.py performance.py meteo.py
│   ├── signals/      catalogue.py registry.py overrides.py
│   ├── n2k/          canid.py fastpacket.py gateway.py scheduler.py
│   │   └── pgns/     one module per PGN group: nav.py wind.py env.py engine.py tanks.py system.py
│   ├── formats/      ydraw.py (Format protocol)
│   ├── transport/    udp.py tcp.py recorder.py (Transport protocol)
│   └── web/          api.py ws.py  static/ index.html app.js gauge.js style.css
└── tests/            mirrors src/n2k_sim
```

## Key interfaces

```python
# tier 1 / tier 2: stateful models advanced by dt
class Environment:  def step(self, t: float, dt: float, cfg: EnvConfig) -> EnvironmentState
class Boat:         def step(self, t: float, dt: float, env: EnvironmentState,
                             cfg: BoatConfig) -> BoatState

# tier 3: one pure function per device, registered with its signals and PGNs
@dataclass(frozen=True)
class DeviceSpec:
    name: str                                   # "gps", "compass", …
    read: Callable[[EnvironmentState, BoatState, StaticData], dict[str, float | None]]
    signals: tuple[str, ...]
    pgns: tuple[PgnSpec, ...]

# calc: pure
def calculate(readings: Mapping[str, float | None], cfg: CalcConfig) -> CalculatedValues

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
- Sequence IDs (SID) are shared per sensor module and incremented per "measurement cycle" so related
  PGNs (e.g. 129026 and 129025 from the GPS) carry the same SID, as real devices do.
- UDP output batches frames into datagrams of ≤ 1400 bytes or every 50 ms, whichever comes
  first (mirrors SH-wg behaviour). TCP writes frames as produced; slow clients are dropped when
  their buffer exceeds 1 MB.

## Configuration & persistence

- `config.py` defines a pydantic `Scenario` (environment, boat, autopilot, static data, overrides,
  output settings). JSON save/load via UI and `--scenario file.json` on the CLI.
- Runtime settings (bind addresses, ports, seed) via CLI flags / environment variables.

## Testing strategy

| Layer | Test |
|---|---|
| geo / units | property tests: wrap angles, vector round trips |
| environment | mean/limits over long runs with fixed seed (TWD stays within ± amplitude, gusts ≤ max) |
| boat | autopilot converges; polar interpolation exact at grid points; leeway sign and range |
| sensors / calc | apparent→true→apparent round trip; set/drift recovers the configured current |
| n2k encoders | golden payloads; decode with an independent Python decoder in tests |
| fast-packet | frame count, sequence counter, padding |
| format / transport | YD RAW line grammar; TCP multi-client; UDP datagram size |
| end-to-end | run 60 s simulated time headless, decode the stream, compare to signal snapshot |

## Extension seams

- New wire format → implement `Format` (Actisense NGT, SeaSmart, NMEA 0183 translator).
- New PGN → add an encoder + `PgnSpec` entry; signals already exist in the registry.
- Waypoint navigation → new `navigation/` model feeding XTE / 129283 / 129284.
