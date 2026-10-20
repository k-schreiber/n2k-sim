# Simulation Models

Deliberately simple: values must be **consistent and plausible**, not physically exact.
Conventions: angles in radians internally, bearings 0..2π clockwise from true north, boat-relative
angles −π..π (positive = starboard). Wind/wave directions are "coming **from**", current set is
"flowing **to**". Time `t` in seconds since simulation start. All randomness comes from one seeded
RNG.

## 1. Wind (over ground)

Parameters (UI, each with auto/fixed):

| Parameter | Default | Meaning |
|---|---|---|
| `twd_mean` | 300° | mean direction wind comes from |
| `tws_mean` | 12 kn | mean speed |
| `osc_amplitude` | 8° | half-range of direction oscillation |
| `osc_period` | 6 min | period of the main oscillation |
| `shift_drift` | 0.5°/min max | slow random walk of the mean (persistent shift); 0 disables |
| `gust_rate` | 1 / 90 s | mean frequency of gusts (Poisson) |
| `gust_strength` | +35 % | peak increase over current base speed |
| `gust_duration` | 20 s | total duration (rise ≈ ⅓, decay ≈ ⅔) |
| `gust_veer` | +5° | direction change during a gust (puffs typically veer) |
| `lull_depth` | 10 % | speed variation between gusts (slow sine, period 3 min) |

Model:

```
twd(t) = twd_mean + walk(t) + osc_amplitude · sin(2π t / osc_period)
                  + 0.3 · osc_amplitude · sin(2π t / (0.37 · osc_period) + φ)   # irregularity
tws(t) = tws_mean · (1 − lull_depth · ½(1 + sin(2π t / 180 s))) · (1 + Σ gust_k(t))
gust_k(t) = gust_strength · shape((t − t_k) / gust_duration)       # shape: smooth 0→1→0
twd  += gust_veer · Σ shape(...)
```

Clamp: TWS ∈ [0, 70 kn]. "Fixed" mode = constant `twd_mean`, `tws_mean`. A manual "gust now"
button schedules a gust immediately.

## 2. Current

`set` (direction to, default 135°), `drift` (default 0.5 kn), optional slow sinusoidal variation
(tidal: drift amplitude ± 50 %, period 12.42 h, off by default). Velocity vector **C**.

## 3. Waves

| Parameter | Default |
|---|---|
| `direction` (from) | 290° |
| `height` H (significant) | 1.0 m |
| `wavelength` λ | 40 m |
| `irregularity` | 0.2 (secondary component amplitude ratio) |

Derived: wave number `k = 2π/λ`; deep-water period `T = sqrt(2πλ/g)` (λ = 40 m → T ≈ 5.1 s);
encounter frequency `ωe = |ω − k·V·cos(μ)|` with `V` = SOG, `μ` = wave direction relative to the
boat's course (0 = head seas). Max wave slope `α = atan(π H / λ)`.

Waves affect **only attitude** (pitch, roll) — see §6.

## 4. Vessel motion

State: position (lat, lon), heading `ψ` (true), STW `v`, rudder `δ`, ROT `r`.

1. **Target STW**
   - sailing: `v_target = polar(TWS_water, |TWA_water|)` (bilinear interpolation; 0 when TWA <
     the polar's minimum angle → "in irons", boat slows down);
   - motoring: `v_target = rpm_to_speed(rpm)` (linear table, default 2500 rpm → 6.5 kn);
   - both: STW is first-order lagged towards the target (`τ = 8 s`) so tacks lose speed briefly.
   - The polar uses wind relative to the **water** (wind over ground minus current), so the boat
     responds correctly when current is present.
2. **Autopilot / helm** (§5) produces a heading rate `r` limited to ± 6°/s (tack ≈ 15 s).
3. **Integration** (dt = 0.1 s):
   ```
   ψ += r·dt
   V_water  = v · (sin ψ, cos ψ)            # east, north
   V_ground = V_water + C
   position += V_ground · dt                 # local flat-earth step, metres → degrees
   SOG = |V_ground|, COG = atan2(V_ground)
   ```
   No leeway (heading = course through water).
4. Log/trip accumulate distance through water; trip resettable from the UI.

## 5. Autopilot

| Mode | Target | Behaviour |
|---|---|---|
| `heading` | true heading ψ* (UI may enter magnetic) | P-controller on heading error |
| `twa` | target TWA (signed) | ψ* = TWD_water − TWA* each tick → follows shifts; sign change = tack/gybe |
| `motor` | heading ψ* and engine RPM | as `heading`, speed from engine |

Controller: `r = clamp(Kp · err, ±r_max)` with `Kp = 0.5 /s`. Rudder angle is a display
derivative: `δ = clamp(r / (0.15 · max(v, 1 m/s)) , ±35°)` plus a small proportional term on wave
yaw so the rudder visibly works in waves. Rate of turn sensor = `r`.

UI helpers: "Tack", "Gybe" (flip TWA sign), "+1°/−1°/+10°/−10°" heading buttons.

## 6. Heel and attitude

- **Heel (static, sailing only):** lookup table `heel_table.json`, rows AWS (kn), columns |AWA|
  (deg), value heel (deg), bilinear interpolation; sign: wind from starboard → heel to port
  (negative roll). Motoring: heel = 0.
  Default shape: 0° below 4 kn, peaks ~22° at AWS 22 kn / AWA 45–60°, ~5° downwind.
- **Roll** = heel + `A_roll · sin(ωe t + φ_r)`, `A_roll = α · |sin μ| · c_roll` (`c_roll = 1.2`).
- **Pitch** = `A_pitch · sin(ωe t + φ_p)`, `A_pitch = α · |cos μ| · c_pitch` (`c_pitch = 0.8`).
- **Yaw** (127257) = heading (yaw angle reported by the attitude sensor = true heading, small
  wave-induced oscillation ±1–2° added to heading itself).
- Clamp roll ±45°, pitch ±20°.

## 7. Polar file format

Tab- or semicolon-separated text (the common `.pol` format used by qtVLM / OpenCPN / Expedition):

```
TWA\TWS	4	6	8	10	12	14	16	20	25
40	2.9	4.0	4.8	5.3	5.6	5.8	5.9	6.0	5.9
52	3.5	4.8	5.7	6.2	6.5	6.7	6.8	6.9	6.9
…
180	2.1	3.0	3.9	4.8	5.6	6.2	6.7	7.4	8.3
```

TWS and boat speed in knots, TWA in degrees. Values outside the table are clamped to the edge.
Ship a mock 40 ft cruiser polar (`mock_cruiser_40.pol`, max ~8.5 kn).

## 8. GNSS and static-like data

- HDOP 0.8, VDOP 1.2, PDOP 1.4, satellites 12, fix type 3D — static, editable.
- GNSS time = system UTC (option: simulation clock if time-scaling is ever added).
- Depth: slow random walk between `depth_min` and `depth_max` (default 12–35 m, period minutes),
  or fixed. Optional "shallow patch" button ramps depth to 3 m for alarm testing.
- Water temperature, air temperature, pressure, humidity: static with optional slow drift (off).
- Magnetic variation: static (default +4.5° E), deviation 0.
