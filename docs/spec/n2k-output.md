# N2K Output

## Gateway (single source)

The simulator does **not** emulate a real multi-device backbone. Like a simple gateway or
multiplexer, it emits every PGN from **one source address** (default `0x23`, configurable) and
announces one ISO address claim (PGN 60928) at start and every 5 min.

| NAME field | Value |
|---|---|
| Unique number | derived from host name (stable per machine) |
| Manufacturer code | 2046 (reserved, avoids impersonating real products) |
| Device class / function | 25 Inter/Intranetwork Device / 136 PC Gateway [GK] |
| Industry group | 4 (marine) |

Sensor modules stay separate in code (tier 3, `DeviceSpec`), so per-device addresses could be
added later inside `n2k/gateway.py` without touching sensors or encoders.

## PGN schedule (defaults, editable per PGN)

| PGN | Name | Interval | Priority | Frame |
|---|---|---|---|---|
| 60928 | ISO Address Claim (gateway) | start + 300 s | 6 | single (PDU1 → 0xFF) |
| 126992 | System Time | 1 s | 3 | single |
| 127245 | Rudder | 100 ms | 2 | single |
| 127250 | Vessel Heading | 100 ms | 2 | single |
| 127251 | Rate of Turn | 100 ms | 2 | single |
| 127257 | Attitude | 100 ms | 3 | single |
| 127258 | Magnetic Variation | 1 s | 6 | single |
| 127488 | Engine Rapid | 100 ms | 2 | single |
| 127489 | Engine Dynamic | 500 ms | 2 | fast (26 B) |
| 127505 | Fluid Level (per tank) | 2.5 s | 6 | single |
| 127508 | Battery Status (per battery) | 1.5 s | 6 | single |
| 128259 | Speed | 1 s | 2 | single |
| 128267 | Water Depth | 1 s | 3 | single |
| 128275 | Distance Log | 1 s | 6 | fast (14 B) |
| 129025 | Position Rapid | 100 ms | 2 | single |
| 129026 | COG & SOG Rapid | 250 ms | 2 | single |
| 129029 | GNSS Position | 1 s | 3 | fast (43 B) |
| 129033 | Time & Date | 1 s | 3 | single |
| 129291 | Set & Drift | 1 s | 3 | single |
| 129539 | GNSS DOPs | 1 s | 6 | single |
| 129540 | GNSS Satellites in View | 1 s | 6 | fast (3 + 12 × n B) |
| 130306 | Wind (apparent) | 100 ms | 2 | single |
| 130306 | Wind ref 4: true, water referenced (TWA/TWS from heading/STW) | 1 s | 2 | single |
| 130306 | Wind ref 3: ground referenced to the centreline (from COG/SOG) | 1 s | 2 | single |
| 130306 | Wind ref 0: ground referenced to true north (from COG/SOG) | 1 s | 2 | single |
| 130310 | Environmental (obsolete) | 500 ms, **off** by default | 5 | single |
| 130311 | Environmental | 500 ms | 5 | single |
| 130312 | Temperature (water) | 2 s | 5 | single |
| 130313 | Humidity | 2 s | 5 | single |
| 130314 | Actual Pressure | 2 s | 5 | single |
| 130316 | Temperature ext. (dew point) | 2 s | 5 | single |

Total ≈ 120 frames/s ≈ 6 kB/s in YD RAW — comparable to a real busy backbone (SH-wg recording:
~100 frames/s).

Not encoded in v1: 130577 (layout uncertain; redundant with 129026/128259/129291), 129283/129284
(no navigation model).

## Encoding rules

- Byte layouts: [pgn-reference.md](pgn-reference.md). Encode **per NMEA 2000 spec**, not per app
  decoder quirks.
- `None` value → field sentinel ("not available").
- Values are rounded to the field resolution and clamped to the field range.
- SID: one counter per sensor module, incremented once per measurement cycle (GPS cycle = 1 s;
  others per emission of their fastest PGN) — a gateway forwards SIDs unchanged.
- Fast-packet sequence counter per PGN (single source).
- 127250 is sent with reference = magnetic and deviation = n/a (fluxgate compass). The
  variation field carries the GPS variation (also sent in 127258): the gateway completes the
  compass data because some software (e.g. TimeZero, qtVLM "Value from NMEA") reads variation only
  from 127250.

## YD RAW format

```
hh:mm:ss.mmm R 09FD0205 00 6A 01 5C 3A FA FF FF\r\n
```

- Timestamp = UTC wall clock of emission, milliseconds.
- CAN ID: 8 uppercase hex digits; data bytes uppercase hex, single spaces; `\r\n` terminator.

## Transports

| Transport | Default | Behaviour |
|---|---|---|
| UDP | enabled, `255.255.255.255:2002` | batches lines into datagrams ≤ 1400 B or 50 ms; target may be a subnet broadcast or a unicast address (e.g. `127.0.0.1` for an emulator with port redirect) |
| TCP server | enabled, `0.0.0.0:2223` | streams to all connected clients; input from clients is read and discarded; client count shown in UI |
| Recorder | off | appends the exact stream to `recordings/YYYYmmdd-HHMMSS.raw` |

Ports deliberately match the SH-wg defaults so a client configured for the boat works unchanged
against the simulator (only the IP differs).
