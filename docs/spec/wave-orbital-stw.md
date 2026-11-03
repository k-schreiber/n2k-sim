# Wave orbital velocity on the paddle wheel

Status: rev 3, implemented (§10). Rev 2 followed the first review (Froude–Krylov force, STW
averaging, opt-in, tier split, STW scale fault). Rev 3 follows the review of the implementation:
κ′ from a signed, smoothed encounter frequency, surge seeded on enable, the wheel reports |speed|,
the mean wave drift is documented, and the tests were tightened. Requested by sailing-analytics:
the boat-speed checks (C4 BSP factor, P4 step detection, planned BSP-from-speed-changes) assume
that STW tracks the boat; in waves it does not.

## 1. Goal

Waves move the water in orbits. The paddle wheel has (almost) no inertia and reads the boat's speed
relative to the **local** water, which includes the orbital velocity. The hull is driven by the same
waves in two ways:
- the pressure gradient that accelerates the water also pushes the hull (Froude–Krylov). Mass
  cancels, so even a heavy hull follows waves that are long compared with the hull;
- drag pulls it towards the water velocity with the boat's speed time constant.

So the hull partly follows the orbit. STW (wheel) and SOG (hull) both oscillate at the encounter
frequency, in proportions that depend on the wavelength relative to the hull and on the encounter
frequency relative to the absolute wave frequency. Under a crest the wheel reads faster in both head
and following seas. The hull slows under a crest in head seas (STW and SOG in antiphase) and speeds
up in following seas, where it can overshoot the orbit (κ′ > 1; STW and SOG in phase, and the wheel's
wave part is reversed compared with the drag-only model). Everything is driven by the **existing**
wave train ([simulation.md §4–6](simulation.md)), so roll, pitch, the masthead wind and STW share
one phase.

**Opt-in:** off by default (§7), so existing scenarios, baselines and the analytics harness don't
change.

**Mean wave drift (modelled):** the encounter phase advances with SOG, which includes the surge, so
the hull spends longer in the part of the cycle where it moves with the waves. It drifts in the
direction the waves travel by

    ⟨w⟩ ≈ −cos μ_w · k·U_h²·Re(H) / (2·ω_e)        (H, U_h: §6)

At 1 m / 5 s: +0.13 kn in following seas, −0.02 kn in head seas; +0.57 kn in following seas at
2 m. This is the hull's counterpart of Stokes drift (surface Stokes drift here ≈ 0.09 kn) and
plausible as a slight push downwind. Mean STW still equals v, because the wheel samples the same
water. Consequence: the processor shows it as current (§7).

Out of scope:
- Stokes drift of the water itself. The Eulerian mean of u at a fixed depth is zero, and the water
  current stays the scenario current.
- Vertical orbital velocity.
- The sideways component (no leeway or drift wobble).
- Hull disturbance of the flow at the transducer.
- Finite water depth and wave spectra.
- The wheel's lever arm below the pitch axis: about 1 m × pitch rate ≈ ±0.2 kn in the default sea.

## 2. Wave train (existing, unchanged)

| Request term | n2k-sim |
|---|---|
| Hs | `waves.height` H, default 1.0 m, amplitude A = H/2 |
| Tp | `waves.period` T, default 5 s; ω = 2π/T, k = ω²/g (deep water) |
| wave_dir (from, true) | `waves.direction`, default 290° (wind default 300°), or the mean TWD with `waves.follow_wind` |
| encounter frequency | ω_e = ω + k·SOG·cos μ, μ = wave_dir − COG (0 = head seas); the phase p advances by \|ω_e\|·dt |
| 2–3 sines | primary + one secondary component i = 2: amplitude (irr/f)·A, wavenumber f·k, phase f·p + 0.7, f = 1.6, `waves.irregularity` default 0.2 |

ω_e is the request's ω − k·V·cos β with β = μ + π measured from the direction the waves travel to.
SOG includes the wave surge w (§4). That is correct for the phase: it is ω·t − k·x of the hull's
actual position. ω_e < 0 means the boat overtakes the waves. The phase and η use |ω_e|, as in the
existing attitude model. The wave pressure response uses the signed value (§4), because overtaking
reverses it. With a current, ω_e uses SOG rather than the speed through water (inherited from the
attitude model).

Per component i: ω₁ = ω, k₁ = k, A₁ = A, phase p₁ = p; ω₂ = √f·ω (deep-water frequency of
wavenumber f·k, used only for amplitudes and κ′), k₂ = f·k, A₂ = (irr/f)·A, p₂ = f·p + 0.7,
encounter frequency ω_e,2 = f·ω_e.

## 3. Orbital velocity

Horizontal orbital velocity at depth z in the direction the waves travel. It is in phase with the
elevation (forward under a crest):

    u(z) = Σᵢ Aᵢ·ωᵢ·e^(−kᵢ·z)·cos pᵢ

Projected onto the **course through water** (CTW = heading_wave + leeway, the existing STW
direction), forward +:

    u_fwd(z) = −u(z)·cos μ_w,   μ_w = wave_dir − CTW

μ_w uses the leeway of the previous step (it changes by far less than 0.1° per step). Head seas:
under a crest the water moves aft (u_fwd < 0), so the wheel reads faster. In beam seas u_fwd ≈ 0.
One angle is used per purpose: μ (from COG) only for the encounter frequency, which is existing
code; μ_w for every projection.

## 4. Hull response (tier 2, boat)

The boat evaluates u_fwd at a fixed hull depth z_h = 0.4 m (constant, not a parameter). For each
component i, the wave surge is wᵢ = κ′ᵢ·u_fwd,i(z_h) + yᵢ:

    dyᵢ/dt = ((1 − κ′ᵢ)·u_fwd,i(z_h) − yᵢ) / τ
    κ′ᵢ = s · κ_L,i · clamp(ωᵢ / ω̄_e,i, −2, 2)
    κ_L,i = sinc(kᵢ·LWL·|cos μ_w| / 2),   sinc(x) = sin x / x

- κ′·u: Froude–Krylov plus added-mass response. The force is ∝ the local water acceleration
  (amplitude ωᵢ·u), integrated at the encounter frequency (÷ ω_e,i).
- ω̄_e is the **signed** encounter frequency low-passed with 20 s. The phase keeps the instantaneous
  value. The smoothing matters: with the instantaneous ω_e, which includes the surge through SOG,
  κ′ swings with the wave and is clipped at the cap in following seas. That made the amplitudes
  18–35 % too small (1–2 m) and added a spurious u·dκ′/dt term. With ω̄_e they match the linear
  response within 1 %. An exact ODE (dw/dt = s·κ_L·∂u/∂t + (u − w)/τ) gives the same amplitudes.
- Overtaking (ω̄_e < 0) reverses κ′. This is reachable with T ≤ 3 s running or motoring at 6–9+ kn,
  where κ_L is small.
- κ_L averages the pressure gradient over the hull length. The depth decay is already in u(z_h).
  For short waves sinc becomes negative, which is correct for the averaged gradient. The drag part
  is not length-averaged. The cap of 2 stops the blow-up near surf-riding (ω_e → 0).
- The y part is the drag pull towards the remaining water velocity with τ = `boat.stw_time_constant_s`
  (8 s, reused; see §8). As ω_e → 0, y → (1 − κ′)·u, so w → u_fwd: the hull moves with the water.
- s = `boat.wave_surge_factor` (default 1). s = 0 gives the drag-only model of the original request.
- w = Σ wᵢ. Two small ODE states, Euler at dt 0.1 s (dt/τ = 0.0125, ≥ 16 samples per encounter
  cycle). No new random draws.
- **Switching on mid-run:** y is seeded with −κ′·u, so w starts at 0 and SOG is continuous; the
  surge then builds up with τ. **Switching off:** w drops to 0 at once (a SOG step of up to the surge
  amplitude), so that "off" stays exactly the model without orbit.

Effects of w:
- **Hull over ground:** current + (v + w) along the CTW. v is the existing STW state (polar or motor
  target, lagged). Position, SOG and COG carry w.
- **Apparent wind and heel:** the hull's ground velocity includes w, so `boat.awa/aws`, the masthead
  wind and the heel target (from `boat.aws`) carry w; the heel's 3 s lag damps it.
- **Unchanged:** the polar target, the boat's leeway and the log use v. The log is a cumulative
  counter and has the same mean.
- **New truth signals:** `boat.wave_surge` = w and `boat.orbital_fwd` = u_fwd(z_h).

BoatState already carries `wave_phase` and `wave_mu`. It also gets the CTW-relative angle μ_w, so the
speed log needs no boat internals.

## 5. Paddle wheel (tier 3, speed log)

The speed log evaluates u_fwd at its own depth z_pw = `sensors.paddlewheel_depth` (default 0.5 m)
from the boat's wave phase and μ_w. The instantaneous, signed wheel speed is

    stw_local = v + w − u_fwd(z_pw)

It is negative when the water flows forward past the wheel (e.g. at rest or very slow in waves).

- **Wheel lag** (optional): a first-order lag on the wave part (w − u_fwd) with
  `sensors.paddlewheel_lag_s` (default 0 = none). It acts on the signed speed (wheel inertia).
- **Direction:** the log counts pulses whichever way the wheel turns, so it uses |v + wave part|.
  STW is never negative and never clamped. At rest in 1 m head seas the hull moves almost with the
  water, and the wheel reads ±0.11 kn back and forth, which the log reports as a mean of 0.07 kn.
- **Reported value:** the speed log reports the mean of |speed| over the last `sensors.stw_average_s`
  (default 1.0 s = the 128259 interval). This is a moving boxcar over the 10 Hz samples, so short
  encounter periods (T = 3 s head seas at 6 kn → T_e ≈ 1.8 s) are averaged over the update interval
  instead of aliased by the 1 s point sample. Well above zero speed the boxcar attenuates the wave
  part by |sinc(π·T_avg/T_e)|: 0.56 at T_e 1.8 s, about 0.88 at 3.6 s.
- **Scale fault:** `sensors.stw_factor` (default 1.0) multiplies the reported STW. This is a true
  paddle-wheel calibration error, independent of the waves, like `invert_pitch`.
- **Signals:** `stw` (128259) = the averaged, rectified, scaled value. The truth signal
  `boat.stw_local` = the signed stw_local at 10 Hz. `boat.stw` = v keeps its meaning. The tests run on
  the 10 Hz truth.

## 6. Expected magnitudes (H 1 m, T 5 s, irr 0, LWL 10.5 m, τ 8 s)

U = A·ω·e^(−k·0.5) = 0.58 m/s = ±1.13 kn at the wheel (k = 0.161 /m). U_h = A·ω·e^(−k·z_h)·|cos μ_w|.

| Case | T_e | ω_e·τ | κ′ | STW (10 Hz) | STW (1 s avg) | SOG |
|---|---|---|---|---|---|---|
| head seas, 6 kn | 3.6 s | 14 | 0.63 | ±0.40 kn | ±0.35 kn | ±0.73 kn (antiphase to STW) |
| following seas, 6.4 kn | 8.6 s | 5.8 | 1.53 | ±0.62 kn | ±0.60 kn | ±1.74 kn (in phase with STW) |
| beam seas | 5.0 s | 10 | — | ≈ 0 | ≈ 0 | ≈ 0 |
| default, port tack (hdg 344°, μ_w −58°, 5.5 kn) | 4.2 s | | | ±0.10 kn | ±0.09 kn | ±0.50 kn |
| default, starboard tack (hdg 254°, μ_w +40°, 5.7 kn) | 3.9 s | | | ±0.22 kn | ±0.19 kn | ±0.64 kn |
| s = 0 (drag only), head seas | 3.6 s | 14 | 0 | ±1.12 kn | ±0.99 kn | ±0.08 kn |
| head seas T = 3 s, 6 kn | 1.8 s | | | ±1.32 kn | ±0.75 kn | |

These figures come from the linear response H = w/u_h = κ′ + (1 − κ′)/(1 + j·ω_e·τ), with the
default headings measured in the simulator. "STW swings while SOG stays smooth" only holds for
waves short compared with the hull. For the analytics this matters: the bias of a
BSP-from-speed-changes estimate (ΔSOG vs ΔSTW) changes sign at κ′ = 1.

**Tack asymmetry in the default scenario:** waves from 290° and wind from 300° give different μ_w
on the two tacks, so the STW wave noise differs by tack (±0.10 vs ±0.22 kn here). As noise in C4's
speed input this can bias the BSP factor by roughly −0.6 to −1.2 % and create a false tack asymmetry
of ~0.5 %. Symmetric test cases need waves from the mean TWD (`waves.follow_wind`, §7) **and**
fixed wind and zero current: the wind's slow random walk and the current (water wind vs ground wind)
otherwise still make the tacks asymmetric.

**Following seas with small ω_e·τ** (e.g. T = 3 s running at 8 kn: ω_e ≈ 0.26 rad/s): the hull
moves with the water, so STW → v and SOG shifts by about ±U for tens of seconds. This is physical,
but the amplitude and frequency tests are limited to ω_e·τ ≥ 3.

## 7. Parameters and off switches

| Parameter | Default | Note |
|---|---|---|
| `waves.orbital` | **false** | opt-in; false = no w, no wheel orbit |
| `waves.follow_wind` | false | scenario option: wave direction = mean TWD (`wind.twd`); `waves.direction` is then ignored |
| `boat.lwl` | 10.5 m | waterline length, for κ_L |
| `boat.wave_surge_factor` | 1.0 | s; 0 = drag-only hull response |
| `sensors.paddlewheel_depth` | 0.5 m | wheel only; the hull uses a fixed 0.4 m |
| `sensors.paddlewheel_lag_s` | 0 s | wheel inertia |
| `sensors.stw_average_s` | 1.0 s | boxcar over the rectified wheel speed |
| `sensors.stw_factor` | 1.0 | STW calibration fault |
| `processor.stw_damping_s` | 0 s | optional processor damping of STW, used for true wind, leeway, VMG, performance and current |
| existing: `waves.height/period/direction/irregularity`, `seed` | | shared with roll, pitch and the masthead wind |

`sensors.paddlewheel_gain` from rev 1 is dropped: the lag models wheel inertia, and a gain on the
wave part only would be confused with the BSP factor.

**Bit-identical** means: `Snapshot.values` for all keys that exist today, and the PGN payloads (YD
RAW timestamps are wall clock), equal to the code before this feature. This holds for each of:
- `waves.orbital = false`, `waves.enabled = false` or `waves.height = 0`, with `stw_factor = 1` and
  `processor.stw_damping_s = 0`, whatever the other new parameters are;
- `waves.follow_wind = false`.

The wheel and processor switches take an explicit branch. In the boat, w is exactly 0.0 when off,
and v + 0.0 = v exactly in IEEE arithmetic.

**Side effects when on** (processor, from the reported STW, undamped unless `stw_damping_s > 0`):
- TWS/TWA (130306 ref 4), VMG and performance % oscillate.
- `leeway_calc` ∝ 1/STW² swings by about ±35 % in head seas with s = 0, and less with the default s.
- COG/SOG − (heading + leeway, STW) = current + u_fwd(z_pw) along the CTW. The oscillating part is
  mostly removed by the processor's 20 s current damping. The mean wave drift (§1) is not: it shows
  as a **false current in the wave travel direction**, 0.13 kn in 1 m following seas (toward 109°
  with waves from 290°), 0.56 kn at 2 m, about 0.02 kn in head seas. For sailing-analytics this is a
  heading-dependent current bias.

## 8. Decisions from the reviews

1. **τ:** reuse `stw_time_constant_s` (8 s). With the Froude–Krylov part, and ω_e·τ ≥ 6 for drag,
   the STW amplitude barely depends on τ. For reference, m_eff/(dR/dV) for 8 t at 12 m is ≈ 65 s at
   2 kn, 30 s at 4 kn, 10 s at 6 kn and 3–5 s at 8 kn. If τ(V) is ever added, cap it at 60 s.
2. **Waves follow wind:** only as the scenario option `waves.follow_wind`.
3. **Secondary component:** f·ω_e encounter with deep-water ω₂ amplitude is acceptable. Its own
   kinematics (phase f·p) imply a frequency f·ω, so its κ′ is 0.79× the self-consistent value; with
   irr ≤ 0.6 it changes the total by a few percent.
4. **Current identity:** the existing `test_sensors_consistent_with_current_in_waves` runs with the
   orbit off and is unchanged. With the orbit on, the identity ground − STW·CTW = current + u_fwd is
   tested in `tests/test_wave_orbital.py` (§9 test 6), with u_fwd computed independently.
5. **Wheel direction:** the wheel reports |speed| (user decision), no clamp at zero.

## 9. Acceptance tests

Unless stated otherwise: fixed wind, zero current, heading mode, irr = 0, `stw_average_s = 0`, and
measurements on the 10 Hz truth (`boat.stw_local − boat.stw`, `boat.wave_surge`). Amplitude =
½ peak-to-peak after a 60 s warm-up. Encounter cases only with ω_e·τ ≥ 3.

1. The off switches in §7 give bit-identical output (as defined there) over a run that includes a
   tack (in the tests: compared with `orbital = false`; against the previous commit: §10).
2. Pinned §6 value: head seas at 6 kn (motoring) give STW ±0.40 kn and SOG ±0.73 kn within 5 %.
3. STW amplitude within 5 % of |H − e^(−k·(z_pw − z_h))|·U_h and surge amplitude within 5 % of |H|·U_h,
   in head and following seas at 1 m and 2 m, and with s = 0. With irr = 0.6, the sum over both
   components within 5 %. Beam seas below 0.1 kn.
4. The dominant STW frequency equals ω_e (zero crossings), within 3 %.
5. Means over ≥ 50 cycles: `stw_local` equals v within 0.02 kn; w within 15 % of the drift formula
   (§1), in head and following seas.
6. Ground velocity − stw_local·CTW = current + u_fwd(z_pw)·CTW within 1e-9, u_fwd from `orbital_fwd`.
7. Sign: in head seas under a crest (cos p = 1), stw_local > v and w < 0.
8. Overtaking reverses the pressure response (signed, clamped ω/ω_e).
9. Switching on mid-run changes SOG by less than 0.05 kn in that step.
10. At rest in head seas: 128259 = |stw_local| without averaging, never negative, positive mean.
11. 128259 with `stw_average_s = 1`: amplitude ≈ |sinc(π·1 s/T_e)| × the 10 Hz amplitude within 10 %.
12. Wheel lag 1 s: amplitude = 10 Hz amplitude / |1 + j·ω_e·1 s| within 5 %.
13. `stw_factor = 1.05` scales 128259 by exactly 1.05 (orbital on and off) and leaves
    `boat.stw_local` unchanged.
14. `processor.stw_damping_s = 5` reduces the `leeway_calc` swing below 25 %.

## 10. Implementation notes

- Code:
  - `boat/model.py`: `_wave_surge`, `surge_ratio`, `orbital_on`, `orbital_components`,
    `orbital_fwd`, the smoothed signed ω_e in `_waves`, and the new BoatState fields `mu_w`,
    `wave_surge`, `orbital_fwd`.
  - `sensors/devices.py`: `paddlewheel_local`, `PaddleWheel` (lag, rectification, boxcar,
    `stw_factor`).
  - `calc/processor.py`: `stw_damping`.
  - `environment/model.py`: `follow_wind`.
  - Tests: `tests/test_wave_orbital.py`.
- `stw_average_s` and `paddlewheel_lag_s` act only while the orbit is on. `stw_factor` acts in both
  cases.
- Bit-identity was checked against the commit before this feature (f478fbb): `Snapshot.values` for
  the existing keys and all PGN payloads over 150 s with a tack, for:
  - the default scenario;
  - `orbital` on with `height = 0`, nonzero lag and averaging;
  - `orbital` on with `enabled = false`;
  - `follow_wind = false` with another wave direction;
  - motor mode;
  - heading mode with T = 8 s and irr 0.6.
- Measured against the linear response (fixed wind from 200°, heading mode, irr 0, 600 s):

  | Case | STW, measured vs linear | surge, measured vs linear | mean surge |
  |---|---|---|---|
  | head seas 1 m, 7.2 kn | −0.6 % | +2.5 % | −0.018 kn |
  | following seas 1 m, 7.3 kn | −0.4 % | −0.2 % | +0.134 kn (formula 0.141) |
  | following seas 2 m | 0.0 % | 0.0 % | +0.566 kn (formula 0.614) |
