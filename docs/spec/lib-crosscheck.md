# Cross-check against the ttlappalainen NMEA2000 library

All 29 encoders were compared field by field with the library's `SetN2kPGN…` functions
(`NMEA2000/src/N2kMessages.cpp`, commit 8d101b3), its enums (`N2kTypes.h`) and its default
message lists (`NMEA2000.cpp`). Every finding below was verified against the library source.

**Result:** byte layouts, field widths, signedness, resolutions, units, "not available" codes and
the fast-packet set (127489, 128275, 129029, 129540) match for every PGN. The fixes are about
semantics (which value goes into a field), a few header defaults, and cosmetics.

## Fix list

**Status (2026-10-21):** A1, A2, B1–B4, C1–C4, D2, D3 and D5 are applied. D1 (127257 at 100 ms)
and D4 (periodic address claim) are kept by decision. With D5, tank instances are fuel 0, fresh
water 1 and 2, black water 3. NMEA Dashboard maps fresh water instances 0/1 to its "water 1/2"
levels, so it now shows fresh water tank 1 (instance 1) as "water 2" and doesn't show tank 2
(instance 2) at all.

### A. Wrong values / semantics on the wire

| # | PGN | Now | Library | Fix |
|---|---|---|---|---|
| A1 | 130306 ref 0 | water-referenced TWD/TWS (`twd`, `tws`: from STW + heading + leeway) | `N2kWind_True_North=0`: "ground referenced, referenced to True North; calculated using COG/SOG" (N2kTypes.h:253) | send ground wind `gwd`/`gws` |
| A2 | 130306 ref 3 | water-referenced TWA/TWS | `N2kWind_True_boat=3`: "to centerline, referenced to ground; calculated using COG/SOG"; `N2kWind_True_water=4`: "referenced to water; calculated using Heading/STW" (N2kTypes.h:257-258) | send water-referenced `twa`/`tws` as **ref 4**; send ground wind angle relative to the centreline (`gwd − heading`) with `gws` as ref 3 |

Impact on NMEA Dashboard: its decoder maps ref 3 → TWA and ignores the angle of ref 4. After the
fix it shows the ground-referenced angle as TWA until ref 4 support is added there.

### B. Header defaults that differ from the library

| # | PGN | Now | Library | Fix |
|---|---|---|---|---|
| B1 | 127258 | priority 7 | `Priority=6` (N2kMessages.cpp:399) | priority 6 |
| B2 | 127258 | age of service (days since 1970) = n/a | written as a real date (N2kMessages.cpp:402) | send the GNSS date |
| B3 | 129029 | integrity 0 ("no integrity checking") | `AddByte(1 \| 0xfc)` — integrity 1 = safe (N2kMessages.cpp:1251) | integrity 1 |
| B4 | 129540 | range residual mode 0 ("used") although residuals are n/a | `0xfc \| Mode`, header default `N2kDD072_Unavailable` (N2kMessages.cpp:1364) | mode 3 (unavailable) |

### C. Cosmetic (reserved bits, enum choice)

| # | PGN | Now | Library | Fix |
|---|---|---|---|---|
| C1 | 127245 | direction order 0xFF (unavailable) | `0xf8 \| order`, default "no direction order" (0) (N2kMessages.cpp:261) | 0xF8 |
| C2 | 60928 | NAME byte 6 reserved bit = 1 | `(DeviceClass&0x7f)<<1` → bit 0 = 0 (NMEA2000.cpp:2806) | bit 0 = 0 |
| C3 | all | out-of-range values clamped to "NA − 3" (e.g. 0xFFFC) | library writes the out-of-range code (e.g. 0xFFFE) | use the library's out-of-range codes |
| C4 | 129539 | desired mode = actual mode (3D) | free choice; real receivers report desired = auto (3) | desired 3, actual 2 |

### D. Choices to confirm (not errors)

| # | Topic | Now | Library | Proposal |
|---|---|---|---|---|
| D1 | 127257 interval | 100 ms | default list says 1000 ms (NMEA2000.cpp:298) | keep 100 ms? (smoother heel/pitch display; many 9-axis sensors send faster) |
| D2 | 130310 / 130311 interval | 2 s | 500 ms (NMEA2000.cpp:311-312) | 500 ms |
| D3 | 129540 interval | 5 s | 1000 ms (NMEA2000.cpp:512) | 1 s |
| D4 | 60928 | re-sent every 300 s unsolicited | sent at start-up and on ISO request (59904); we don't read requests | keep (harmless, helps clients that connect later) |
| D5 | 127505 instances | instances repeat across fluid types (fuel 0, water 0/1, black water 0) | header doc: "best to have instance unique" | unique instances 0–3 |

### Not verifiable against the library

129291 (Set & Drift, Rapid Update) has no encoder in the library. Our layout (SID, set reference,
set u16 0.0001 rad, drift u16 0.01 m/s, reserved) and priority 3 follow canboat.
