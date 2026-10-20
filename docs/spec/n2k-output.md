# N2K Output

## Virtual devices

A real backbone has several devices, each with its own source address and NAME. The simulator
claims addresses for these (address claim PGN 60928 at start and every 5 min — not required by the
standard, but lets late listeners learn the devices; v1 does not answer ISO requests).

| Device | Source | Device class / function [GK] | PGNs |
|---|---|---|---|
| GPS | 0x01 | 60 Navigation / 145 Ownship Position | 126992, 129025, 129026, 129029, 129033, 129539, 127258 |
| Compass / attitude | 0x02 | 60 Navigation / 140 Heading Sensor | 127250, 127251, 127257 |
| Speed log | 0x03 | 60 / 155 Speed Sensors | 128259, 128275, 130312 (water temp) |
| Depth sounder | 0x04 | 60 / 130 Bottom Depth | 128267 |
| Wind sensor | 0x05 | 85 External Environment / 130 Atmospheric | 130306 (apparent) |
| Instrument processor | 0x06 | 60 / 135 (display) | 130306 (true ref 3 + ref 0), 129291 |
| Rudder sensor | 0x07 | 40 Steering / 155 Rudder | 127245 |
| Engine gateway | 0x08 | 50 Propulsion / 140 Engine | 127488, 127489 |
| Tank sender(s) | 0x09 | 75 Sensor Comm / 150 Fluid Level | 127505 |
| Battery monitor | 0x0A | 35 Electrical Generation / 170 Battery | 127508 |
| Weather station | 0x0B | 85 / 130 | 130310, 130311, 130313, 130314, 130316 (dew point) |

Manufacturer code: 2046 (reserved/"unknown") to avoid impersonating real products.

## PGN schedule (defaults, editable per PGN)

| PGN | Name | Interval | Priority | Frame |
|---|---|---|---|---|
| 60928 | ISO Address Claim | start + 300 s | 6 | single (PDU1 → 0xFF) |
| 126992 | System Time | 1 s | 3 | single |
| 127245 | Rudder | 100 ms | 2 | single |
| 127250 | Vessel Heading | 100 ms | 2 | single |
| 127251 | Rate of Turn | 100 ms | 2 | single |
| 127257 | Attitude | 100 ms | 3 | single |
| 127258 | Magnetic Variation | 1 s | 7 | single |
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
| 130306 | Wind (apparent) | 100 ms | 2 | single |
| 130306 | Wind (true boat-ref, ground-ref) | 1 s each | 2 | single |
| 130310 | Environmental (obsolete) | 2 s, **off** by default | 5 | single |
| 130311 | Environmental | 2 s | 5 | single |
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
- SID: one counter per device, incremented once per measurement cycle (GPS cycle = 1 s; others per
  emission of their fastest PGN).
- Fast-packet sequence counter per (PGN, source).

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
