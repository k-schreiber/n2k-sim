# PGN Encoding Reference

Byte-level reference for the encoders. Extracted from the NMEA Dashboard decoders
(`nmea_dashboard/lib/state/parsing/2000/`) and the wellenvogel gateway, completed from general
knowledge (canboat / NMEA 2000 / ttlappalainen NMEA2000 library).

- **[APP]** = verified in the NMEA Dashboard decoder (file in `lib/state/parsing/2000/`).
- **[GK]** = general knowledge, not verified against a decoder in the reference repos. Verify against
  canboat before relying on it for interoperability with other software.

**Policy:** the simulator encodes **per the NMEA 2000 specification**, not per app quirks. Where
the app deviates (marked ⚠), the deviation is an app bug to be found by testing.

## 0. Conventions

- Little endian for all multi-byte fields. Reserved bits/bytes = 1 (0xFF). [APP common.dart]
- Single-frame PGNs are always exactly **8 bytes** (pad 0xFF); the app drops other lengths.
- "Not available" sentinels: u8 0xFF, u16 0xFFFF, i16 0x7FFF, u24 0xFFFFFF, u32 0xFFFFFFFF,
  i32 0x7FFFFFFF, i64 0x7FFFFFFFFFFFFFFF. (Decoders treat i16 ≥ 0x7FFD etc. as null.)
- Angles: radians × 10⁴ (0.0001 rad). Unsigned for 0..2π, signed for ±π.
- Speeds: 0.01 m/s. Temperatures: Kelvin, 0.01 K (130316: 0.001 K, u24).
- Date: u16 days since 1970-01-01 UTC. Time: u32 0.0001 s since midnight UTC.
- Percentages (humidity, fluid level): 0.004 % per bit (25000 = 100 %).

## 1. CAN ID (29-bit) and YD RAW line

```
bits 28..26 priority | bit 25 reserved (0) | bit 24 data page | 23..16 PF | 15..8 PS | 7..0 source
PDU1 (PF < 240):  PGN = DP<<16 | PF<<8          PS = destination (0xFF = global)
PDU2 (PF >= 240): PGN = DP<<16 | PF<<8 | PS
id = prio<<26 | DP<<24 | PF<<16 | PS<<8 | SA
```

Example: PGN 130306 (0x1FD02), priority 2, source 0x23 → `0x09FD0223`.
All PGNs used here are PDU2 except 60928 (PF 0xEE, PDU1).

YD RAW line (one CAN frame): `hh:mm:ss.mmm R XXXXXXXX B0 B1 … Bn\r\n`

- Exactly one space between tokens (a double space makes the app drop the line).
- Direction `R` (the app ignores `T`). 1–8 data bytes, two uppercase hex digits each.
- Timestamp: UTC time of day with milliseconds (the app ignores it, other tools may not).
- Multiple lines may be packed into one UDP datagram (SH-wg concatenates up to ~1000 bytes / 100 ms).

## 2. Fast-packet framing

- Frame 0: `B0 = seq<<5 | 0`, `B1 = total length (1..223)`, `B2..B7` = payload[0..5].
- Frame k ≥ 1: `B0 = seq<<5 | k`, `B1..B7` = next 7 payload bytes; pad last frame with 0xFF.
- `seq` (0–7) increments per message **per (PGN, source)**; same in all frames of a message.
- Frames of one message are sent back-to-back with the same CAN ID.
- Frame count = `1 + ceil(max(0, len − 6) / 7)`.
- ⚠ The app treats exactly these PGNs as fast-packet: 127489, 128275, 129029, 129284, 130577
  (spec-consistent for this PGN set; 126996 product info would also be fast-packet).

## 3. Per-PGN layouts

### 60928 ISO Address Claim — single, PDU1 to 0xFF, priority 6 [GK]
| Off | Field |
|---|---|
| 0–3 | u32: bits 0–20 unique number, bits 21–31 manufacturer code |
| 4 | bits 0–2 device instance lower, bits 3–7 device instance upper |
| 5 | device function |
| 6 | bit 0 reserved (1), bits 1–7 device class |
| 7 | bits 0–3 system instance, bits 4–6 industry group (4 = marine), bit 7 arbitrary address capable |

### 126992 System Time — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID [GK] |
| 1 | u8 | bits 0–3 source (0 = GPS) [GK] |
| 2 | u16 | date [APP] |
| 4 | u32 | time [APP] |

### 127245 Rudder — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | instance [GK] |
| 1 | u8 | bits 0–2 direction order [GK] |
| 2 | i16 | angle order, 0.0001 rad [GK] |
| 4 | i16 | position, 0.0001 rad, starboard positive [APP; app rejects outside ±90°] |
| 6 | u16 | reserved |

### 127250 Vessel Heading — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID |
| 1 | u16 | heading, 0.0001 rad [APP] |
| 3 | i16 | deviation, 0.0001 rad [GK] |
| 5 | i16 | variation, 0.0001 rad, **east positive** [APP reads] |
| 7 | u8 | bits 0–1 reference: 0 true, 1 magnetic [APP] |

⚠ App computes `true = magnetic − variation`; spec: `true = magnetic + variation(E+)`.

### 127251 Rate of Turn — single
| 0 | u8 | SID | · | 1 | i32 | rate, 3.125×10⁻⁸ rad/s, starboard positive [APP] | · | 5–7 reserved

### 127257 Attitude — single [APP]
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID |
| 1 | i16 | yaw, 0.0001 rad |
| 3 | i16 | pitch, 0.0001 rad (bow up positive) |
| 5 | i16 | roll, 0.0001 rad (starboard down positive) |
| 7 | u8 | reserved |

### 127258 Magnetic Variation — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID [GK] |
| 1 | u8 | bits 0–3 source (e.g. 8 = WMM2020) [GK] |
| 2 | u16 | age of service, days [GK] |
| 4 | i16 | variation, 0.0001 rad, east positive [APP] |
| 6 | u16 | reserved |

### 127488 Engine Parameters, Rapid — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | engine instance (0 = port/single) [APP] |
| 1 | u16 | speed, 0.25 rpm [APP] |
| 3 | u16 | boost pressure, 100 Pa [GK] |
| 5 | i8 | tilt/trim % [GK] |
| 6 | u16 | reserved |

### 127489 Engine Parameters, Dynamic — fast-packet, 26 bytes
| Off | Type | Field |
|---|---|---|
| 0 | u8 | instance [APP] |
| 1 | u16 | oil pressure, 100 Pa [APP] |
| 3 | u16 | oil temperature, 0.1 K [GK] |
| 5 | u16 | coolant temperature, 0.01 K [APP] |
| 7 | i16 | alternator potential, 0.01 V [APP] |
| 9 | i16 | fuel rate, 0.1 L/h [GK] |
| 11 | u32 | total engine hours, s [GK] |
| 15 | u16 | coolant pressure, 100 Pa [GK] |
| 17 | u16 | fuel pressure, 1000 Pa [GK] |
| 19 | u8 | reserved |
| 20 | u16 | discrete status 1 [GK] |
| 22 | u16 | discrete status 2 [GK] |
| 24 | i8 | engine load % [GK] |
| 25 | i8 | engine torque % [GK] |

### 127505 Fluid Level — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | low nibble instance, high nibble type (0 fuel, 1 fresh water, 2 grey, 3 live well, 4 oil, 5 black water) [APP + GK] |
| 1 | i16 | level, 0.004 % [APP; rejects outside 0–100 %] |
| 3 | u32 | capacity, 0.1 L [GK] |
| 7 | u8 | reserved |

### 127508 Battery Status — single [GK only; app has no decoder]
| 0 | u8 | instance | 1 | i16 | voltage 0.01 V | 3 | i16 | current 0.1 A | 5 | u16 | temperature 0.01 K | 7 | u8 | SID |

### 128259 Speed — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID |
| 1 | u16 | speed water referenced, 0.01 m/s [APP] |
| 3 | u16 | speed ground referenced, 0.01 m/s [APP] — send 0xFFFF (log devices don't know SOG) |
| 5 | u8 | water reference type (0 paddle wheel) [GK] |
| 6 | u8 | bits 0–3 speed direction [GK] |
| 7 | u8 | reserved |

### 128267 Water Depth — single [APP]
| 0 | u8 | SID | 1 | u32 | depth below transducer, 0.01 m | 5 | i16 | offset, 0.001 m (+ = to waterline, − = to keel) | 7 | u8 | range, 10 m [GK] |

### 128275 Distance Log — fast-packet, 14 bytes [APP]
| 0 | u16 | date | 2 | u32 | time | 6 | u32 | log, m | 10 | u32 | trip, m |

### 129025 Position, Rapid — single [APP]
| 0 | i32 | latitude, 10⁻⁷ deg | 4 | i32 | longitude, 10⁻⁷ deg |

### 129026 COG & SOG, Rapid — single [APP]
| 0 | u8 | SID | 1 | u8 | bits 0–1 COG reference (0 true) | 2 | u16 | COG 0.0001 rad | 4 | u16 | SOG 0.01 m/s | 6 | reserved |

### 129029 GNSS Position Data — fast-packet, 43 bytes (no reference stations)
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID [GK] |
| 1 | u16 | date [APP] |
| 3 | u32 | time [APP] |
| 7 | i64 | latitude, 10⁻¹⁶ deg [APP] |
| 15 | i64 | longitude, 10⁻¹⁶ deg [APP] |
| 23 | i64 | altitude, 10⁻⁶ m [GK] |
| 31 | u8 | bits 0–3 GNSS type (0 GPS), bits 4–7 method (1 GNSS fix, 2 DGNSS) [GK] |
| 32 | u8 | bits 0–1 integrity [GK] |
| 33 | u8 | number of satellites [GK] |
| 34 | i16 | HDOP, 0.01 [APP] |
| 36 | i16 | PDOP, 0.01 [GK] |
| 38 | i32 | geoidal separation, 0.01 m [GK] |
| 42 | u8 | number of reference stations = 0 [GK] |

### 129033 Time & Date — single [APP]
| 0 | u16 | date | 2 | u32 | time | 6 | i16 | local offset, minutes [GK] |

### 129283 Cross Track Error — single
| 0 | u8 | SID | 1 | u8 | XTE mode / nav terminated [GK] | 2 | i32 | XTE 0.01 m [APP] | 6 | reserved |

### 129284 Navigation Data — fast-packet, 34 bytes
Offsets [APP for 1, 5, 14; rest GK]: 0 SID · 1 u32 distance to wpt 0.01 m · 5 u8 bits 0–1 bearing
reference (0 true) · 6 u32 ETA time · 10 u16 ETA date · 12 u16 bearing origin→dest · 14 u16
bearing position→dest · 16 u32 origin wpt id · 20 u32 dest wpt id · 24 i32 dest lat 10⁻⁷ · 28 i32
dest lon 10⁻⁷ · 32 i16 closing velocity 0.01 m/s.

### 129291 Set & Drift, Rapid — single [APP]
| 0 | u8 | SID | 1 | u8 | bits 0–1 set reference (0 true) | 2 | u16 | set 0.0001 rad | 4 | u16 | drift 0.01 m/s | 6 | reserved |

### 129539 GNSS DOPs — single
| 0 | u8 | SID | 1 | u8 | desired/actual mode (2 = 3D) [GK] | 2 | i16 | HDOP 0.01 [APP] | 4 | i16 | VDOP 0.01 [GK] | 6 | i16 | TDOP 0.01 [GK] |

### 129540 GNSS Satellites in View — fast-packet, 3 + 12·n bytes [GK]
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID |
| 1 | u8 | bits 0–1 range residual mode, rest reserved |
| 2 | u8 | satellites in view n |
| per satellite (12 B) | u8 PRN · i16 elevation 0.0001 rad · u16 azimuth 0.0001 rad · i16 SNR 0.01 dB · i32 range residual 10⁻⁵ m · u8 bits 0–3 status (0 not tracked, 1 tracked, 2 used, 3–5 with differential) |

Not decoded by NMEA Dashboard. Verify against canboat before relying on it.

### 130306 Wind Data — single [APP]
| 0 | u8 | SID | 1 | u16 | speed 0.01 m/s | 3 | u16 | angle 0.0001 rad (0..2π) | 5 | u8 | bits 0–2 reference | 6 | reserved |

Reference (ttlappalainen `tN2kWindReference`, N2kTypes.h:252): 0 ground referenced to true north
(from COG/SOG), 1 ground referenced to magnetic north, 2 apparent, 3 ground referenced to the
centreline (from COG/SOG), 4 water referenced to the centreline (from heading/STW).
The simulator sends 2 (AWA/AWS), 4 (instrument TWA/TWS), 3 (ground wind angle/speed) and
0 (ground wind direction/speed). ⚠ NMEA Dashboard decodes ref 3 as TWA and ignores the angle of
ref 4.
Boat-relative angles are encoded 0..2π (port side = 2π − |angle|).

### 130310 Environmental Parameters (obsolete) — single [APP]
| 0 | u8 | SID | 1 | u16 | water temp 0.01 K | 3 | u16 | outside air temp 0.01 K | 5 | u16 | pressure, hPa | 7 | reserved |

### 130311 Environmental Parameters — single
| Off | Type | Field |
|---|---|---|
| 0 | u8 | SID |
| 1 | u8 | bits 0–5 temperature source, bits 6–7 humidity source [GK spec] |
| 2 | u16 | temperature, 0.01 K [APP] |
| 4 | i16 | humidity, 0.004 % [APP] |
| 6 | u16 | pressure, hPa [APP] |

⚠ App reads the temperature source as `byte1 >> 2` instead of `byte1 & 0x3F`.
Temperature source enum: 0 sea, 1 outside, 2 inside, 3 engine room, 4 main cabin, … 9 dew point.

### 130312 Temperature — single [APP]
| 0 | u8 | SID | 1 | u8 | instance | 2 | u8 | source | 3 | u16 | actual 0.01 K | 5 | u16 | set 0.01 K | 7 | reserved |

### 130313 Humidity — single
| 0 | u8 | SID | 1 | u8 | instance | 2 | u8 | source (0 inside, 1 outside) [GK] | 3 | i16 | actual 0.004 % [APP] | 5 | i16 | set | 7 | reserved |

### 130314 Actual Pressure — single [APP]
| 0 | u8 | SID | 1 | u8 | instance | 2 | u8 | source (0 atmospheric, 7 oil, …) | 3 | i32 | pressure 0.1 Pa | 7 | reserved |

### 130316 Temperature, Extended Range — single [APP]
| 0 | u8 | SID | 1 | u8 | instance | 2 | u8 | source | 3 | u24 | actual 0.001 K | 6 | u16 | set 0.1 K |

⚠ App maps source 2 to dew point; spec: 2 = inside, 9 = dew point.

### 130577 Direction Data — fast-packet, 14 bytes
| 0 | u8 | data mode / reference bits [GK, uncertain] | 1 | u8 | app requires bits 2–3 = 0 for "true" [APP] |
| 2 | u16 | COG | 4 | u16 | SOG | 6 | u16 | heading | 8 | u16 | STW | 10 | u16 | set | 12 | u16 | drift |

Layout of bytes 0–1 is uncertain; verify against canboat before enabling this PGN.

## 4. Decoder quirks found in NMEA Dashboard (app bugs to fix there)

1. 127250 magnetic → true conversion subtracts east-positive variation (should add).
2. 130311 temperature source decoded from `byte1 >> 2` instead of the low 6 bits.
3. 130316 source 2 mapped to dew point (spec 9).
4. Variation sign: 0183 parsers store variation west-positive, the N2K parsers store the raw
   east-positive value in the same `variation` property.

## 5. Magnetic variation sign — evidence (ttlappalainen NMEA2000 / NMEA0183)

Checked against `ttlappalainen/NMEA2000` (commit 8d101b3) and `ttlappalainen/NMEA0183`:

- **Library core (N2kMessages.cpp)** stores the 127250/127258 variation as a plain signed value; no
  sign conversion. The header documents 127250 as "the variation field can be used to correct the
  Magnetic heading to produce a True heading", without naming the sign.
- **NMEA0183 library** defines the convention explicitly: `NMEA0183ParseRMC` negates the value for
  `W` (→ east positive), and `NMEA0183SetHDG`/`SetRMC` write `E` for values ≥ 0. So in this
  ecosystem variation is **east positive**, and therefore **true = magnetic + variation**.
- **Example `NMEA2000ToNMEA0183/N2kDataToNMEA0183.cpp` is internally inconsistent:** line 96
  `Heading-=Variation` (mag→true), line 122 `MagneticHeading = Heading+Variation` and line 166
  `COG-=Variation` treat variation as west positive, while line 163 `MCOG = COG-Variation` treats it
  as east positive. It also passes the *true* heading into HDG's magnetic-heading field.
- The SH-wg firmware copied lines 96/HDG from this example; the wellenvogel gateway does it right
  (`Heading+=Variation`). NMEA Dashboard's 127250 decoder subtracts as well.
- **qtVLM** does not subtract: it takes variation from a configurable source (forced value, RMC
  sentence, or World Magnetic Model — *Boat → Boat settings → Variation*). On a pure N2K stream
  there is no RMC, so with "from RMC" it applies no variation and treats the magnetic 127250
  heading as true (confirmed by test: with simulator variation = 0 its current matches). Use WMM
  or a forced value in qtVLM; the simulator also fills the 127250 variation field so a "from NMEA"
  source has a value to read. Other software (e.g. TimeZero) reads variation only from the
  127250 variation field, not from 127258.

The simulator follows the documented convention: east positive, true = magnetic + variation.
