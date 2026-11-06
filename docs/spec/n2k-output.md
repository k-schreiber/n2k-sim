# N2K Output

**canboat is the source of truth for NMEA 2000** (`docs/canboat.json` in the canboat repository):
PGN layouts, priorities, field resolutions and lookups follow it, also where an application or
library differs. `tests/n2k/test_canboat_conformance.py` checks every PGN against it (framing,
length, priority, reserved bits, interval) when the repository sits next to n2k-sim. Differences
on purpose: 127257 runs at 10 Hz (canboat: 1 Hz), because the analysis needs it, and 130306 sends
each wind reference at its own rate.

## Gateway (single source)

The simulator does **not** emulate a real multi-device backbone. Like a simple gateway or
multiplexer, it emits every PGN from **one source address** (default `0x23`, configurable). On the
bus it is one properly identified device.

| NAME field | Value |
|---|---|
| Unique number | `device.unique_number`, default derived from the host name (stable per machine, so the CAN Name survives restarts; never the all-ones "unset" value) |
| Manufacturer code | 2046 (unassigned in canboat, avoids impersonating real products; the ttlappalainen library's default) |
| Device class / function | 25 Internetwork device / 136 NMEA Network Gateway |
| Device instance, system instance | `device.device_instance`, `device.system_instance`, default 0 |
| Industry group | 4 (marine), arbitrary address capable |

## Device identification and network management

Implemented in `n2k/device.py`. The reference for what a network manager needs is [Signal K's
device management](https://demo.signalk.org/documentation/Configuration/NMEA_2000_Device_Management.html):
it keys devices by CAN Name (the NAME in 60928), sends ISO requests for 60928, 126996 and 126998 to
each address and writes instances and labels with 126208. That **needs a bidirectional link**, so
the TCP port behaves like a YDWG gateway and reads what clients send.

**Sent unasked:** 60928, 126996 and 126998 at the start, when a TCP client connects and every 60 s
(receive-only links such as UDP can't ask, and a real bus would have shown them at power-up), and
the heartbeat 126993 every 60 s.

| PGN | Identity |
|---|---|
| 126996 Product Information | NMEA 2000 version 2.101, product code 2000, model `n2k-sim`, software version = package version, model version `Simulator`, serial = unique number, level B, 1 LEN |
| 126998 Configuration Information | descriptions 1 and 2 (`device.installation_description1/2`, default `Simulator`, empty), manufacturer information `Simulated data, not for navigation` |
| 126464 PGN lists | transmit list follows the enabled PGNs; receive list 59904, 60928, 126208 |

**Answered** (from a client on the TCP port, frames addressed to this device or global):

| Input | Answer |
|---|---|
| 59904 ISO Request | the requested PGN: 60928, 126996, 126998, 126464 (both lists, addressed to the requester) or any enabled scheduled PGN; else 59392 NAK if the request was addressed to this device (none to a global request or to a device without address, 254) |
| 60928 Address Claim on this address | ISO contention: the lower NAME wins. Lower: claim again. Higher: move to the next free address and claim it (the Output view shows the address in use) |
| 126208 Command | sets device and system instance (60928 fields 3, 4, 8) and installation descriptions (126998 fields 1, 2); per-parameter Acknowledge, then a new claim (the NAME changed) or 126998. Other PGNs: Not supported |
| 126208 Request | sends the PGN and acknowledges; a change of transmission interval is refused with "Transmit Interval/Priority not supported" (intervals belong to the scenario) |
| 126208 Read/Write Fields | Acknowledge "Read or Write not supported" |

Changes from the bus end up in the scenario (`device` section), so "Save scenario" keeps them. A
change of instance changes the CAN Name, as on a real device.

Not implemented: ISO Commanded Address (65240, needs ISO transport), the battery/temperature
instance commands Signal K offers (acknowledged as not supported), fast-packet input of other PGNs.

Client input format: `XXXXXXXX B0 B1 ...` as canboatjs and YDWG clients send it, or a full YD RAW
line; other lines are ignored. canboatjs sends a fast-packet message of exactly 8 bytes as one plain
frame without the fast-packet header, which the assembler accepts.

**Verified** with signalk-server 2.34 (`ydwg02-canboatjs`, `createDevice: true`): it lists the
simulator with CAN Name, model, version and serial next to its own device on address 100, discovery
finds both, and `n2kConfigDevice` changed the device instance and description 2.

**126993 Data transmit offset:** canboat defines it in milliseconds (60 s = 60000, changed from
centiseconds in canboat #696 and #1003). The ttlappalainen library and the schema bundled with
signalk-server 2.34 still use 0.01 s, so Signal K shows 10 minutes. Canboat is followed.

Do not confuse the TCP input with bus access: nothing a client sends is forwarded, and the UI's
login-free warning applies to the port too (a client can change the instances and labels of this
simulator, nothing else).

Sensor modules stay separate in code (tier 3, `DeviceSpec`), so per-device addresses could be
added later inside `n2k/gateway.py` without touching sensors or encoders.

## PGN schedule (defaults, editable per PGN)

| PGN | Name | Interval | Priority | Frame |
|---|---|---|---|---|
| 60928 | ISO Address Claim | start, connect, 60 s | 6 | single (PDU1 → 0xFF) |
| 126992 | System Time | 1 s | 3 | single |
| 126993 | Heartbeat | 60 s | 7 | single |
| 126996 | Product Information | start, connect, 60 s, on request | 6 | fast (134 B) |
| 126998 | Configuration Information | start, connect, 60 s, on request | 6 | fast |
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
| TCP server | enabled, `0.0.0.0:2223` | streams to all connected clients; reads what they send and answers network management (above); client count shown in UI |
| Recorder | off | appends the exact stream to `recordings/YYYYmmdd-HHMMSS.raw` |

Ports deliberately match the SH-wg defaults so a client configured for the boat works unchanged
against the simulator (only the IP differs).
