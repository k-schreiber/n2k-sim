"""Tier 2: the boat. Reads the environment (never the sensors) and produces the boat's true state.

Lean by design: first-order speed response, P-controlled autopilot, heel from a lookup table,
leeway from the classic K·heel/STW² formula, wave-driven attitude and optional wave surge (see
docs/spec/simulation.md and docs/spec/wave-orbital-stw.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from n2k_sim import geo
from n2k_sim.boat.tables import HeelTable, Polar
from n2k_sim.config import Scenario
from n2k_sim.environment.state import EnvironmentState
from n2k_sim.units import KNOT, kn_to_ms, ms_to_kn

KP = 0.5  # autopilot gain, 1/s
HEEL_TIME_CONSTANT = 3.0  # s
MAX_LEEWAY = 10.0  # deg
MAX_RUDDER = math.radians(35.0)
MAX_ROLL = math.radians(45.0)
MAX_PITCH = math.radians(20.0)
ROLL_FACTOR = 1.2
PITCH_FACTOR = 0.8
YAW_FACTOR = 0.25
SECONDARY_FREQ = 1.6
HULL_DEPTH = 0.4  # m, depth at which the orbital velocity drives the hull
SURGE_RATIO_CAP = 2.0  # max |ω/ω_e| in the wave pressure response (stops the blow-up near surfing)
ENCOUNTER_SMOOTHING = 20.0  # s, low-pass of ω_e for the wave pressure response (not for the phase)


@dataclass(frozen=True)
class BoatState:
    lat: float  # deg
    lon: float  # deg
    heading: float  # rad true, steady heading the autopilot steers
    heading_wave: float  # rad true, heading including wave-induced yaw (what a compass sees)
    rot: float  # rad/s, rate of change of heading_wave
    ctw: float  # rad, course through water
    stw: float  # m/s
    target_stw: float  # m/s, polar or motor target
    leeway: float  # rad, + = slipping to starboard
    heel: float  # rad, + = starboard down
    roll: float  # rad, heel + waves
    pitch: float  # rad, bow up +
    rudder: float  # rad, starboard +
    sog: float  # m/s
    cog: float  # rad
    aws: float  # m/s, true apparent wind (what a perfect masthead sensor sees)
    awa: float  # rad, -π..π, + = from starboard
    wws: float  # m/s, wind relative to water
    wwd: float  # rad, from
    motoring: bool
    rpm: float
    log_total: float  # m
    log_trip: float  # m
    wave_phase: float = 0.0  # rad, encounter phase of the wave at the boat
    wave_mu: float = 0.0  # rad, direction the waves come from relative to the course (0 = ahead)
    yaw_wave: float = 0.0  # rad, wave-induced yaw (heading_wave − heading)
    roll_rate: float = 0.0  # rad/s, d(roll)/dt (heel change + waves), + = rolling to starboard
    pitch_rate: float = 0.0  # rad/s, d(pitch)/dt, + = bow rising
    mu_w: float = 0.0  # rad, direction the waves come from relative to the course through water
    wave_surge: float = 0.0  # m/s, hull velocity along the course through water caused by the orbit
    orbital_fwd: float = 0.0  # m/s, orbital water velocity along the course through water at the hull


class Boat:
    def __init__(self, cfg: Scenario, polar: Polar, heel_table: HeelTable):
        self.polar = polar
        self.heel_table = heel_table
        self._lat = cfg.boat.lat
        self._lon = cfg.boat.lon
        self._heading = math.radians(cfg.autopilot.heading)
        self._stw = 0.0
        self._heel = 0.0
        self._leeway = 0.0
        self._wave_phase = 0.0
        self._wave_mu = 0.0
        self._yaw = 0.0  # rad, wave-induced yaw; turns the hull and therefore its track
        self._sog = 0.0
        self._cog = 0.0
        self._last_heading_wave: float | None = None
        self._last_damping: float | None = None
        self._last_mu: float | None = None
        self._omega_e_slow: float | None = None  # rad/s, signed encounter frequency, low-passed
        self._surge = 0.0  # m/s, wave surge w (exactly 0 when the orbital effect is off)
        self._surge_y = [0.0, 0.0]  # drag-driven part of w per wave component
        self._surging = False  # orbital effect active at the last step
        self._log_total = 0.0
        self._log_trip = 0.0
        self._initialised = False
        self._twa = 0.0  # rad, signed TWA to the water wind at the last step
        self._turn_dir = 0  # forced turn direction during a tack/gybe: +1 starboard, -1 port, 0 shortest

    def maneuver(self, toward_wind: bool) -> None:
        """Forces the next course change through the wind (tack) or away from it (gybe)."""
        side = 1 if self._twa >= 0 else -1  # wind from starboard: turning to starboard heads up
        self._turn_dir = side if toward_wind else -side

    def reset_trip(self) -> None:
        self._log_trip = 0.0

    def teleport(self, lat: float, lon: float) -> None:
        self._lat, self._lon = lat, lon

    def step(self, t: float, dt: float, env: EnvironmentState, cfg: Scenario) -> BoatState:
        wind_ground = geo.wind_from_vector(env.wind_speed, env.wind_dir)
        current = geo.vector(env.current_drift, env.current_set)
        wws, wwd = geo.wind_from_polar(geo.sub(wind_ground, current))
        ap = cfg.autopilot
        motoring = ap.mode == "motor"

        if not self._initialised:
            # Start on the requested course instead of turning onto it.
            self._heading = self._target_heading(cfg, wwd)
            self._initialised = True

        # Autopilot: P-controller on heading error, limited turn rate.
        delta = self._target_heading(cfg, wwd) - self._heading
        err = geo.wrap_pi(delta)
        if self._turn_dir and abs(err) > math.radians(2.0):
            err = self._turn_dir * ((self._turn_dir * delta) % (2 * math.pi))
        else:
            self._turn_dir = 0
        r_max = math.radians(cfg.boat.max_turn_rate)
        rate = max(-r_max, min(r_max, KP * err))
        self._heading = geo.wrap_2pi(self._heading + rate * dt)

        # Speed: first-order lag towards polar or motor speed.
        twa_water = geo.wrap_pi(wwd - self._heading)
        self._twa = twa_water
        if motoring:
            target = kn_to_ms(ap.rpm / 1000.0 * cfg.boat.motor_speed_per_1000rpm)
        else:
            target = kn_to_ms(self.polar.boat_speed(ms_to_kn(wws), math.degrees(twa_water)))
        tau = max(cfg.boat.stw_time_constant_s, 0.1)
        self._stw += (target - self._stw) * min(dt / tau, 1.0)

        # Wave-induced motion (encounter frequency from the previous ground track). Yaw turns the
        # whole hull, so it changes the track as well as what the compass sees.
        roll_w, pitch, self._yaw, roll_w_rate, pitch_rate = self._waves(dt, env, self._sog, self._cog)

        # Wave surge: the orbiting water moves the hull along its course through water. μ_w uses the
        # leeway of the previous step (it changes by far less than 0.1° per step).
        mu_w = geo.wrap_pi(env.wave_dir - (self._heading + self._yaw + self._leeway))
        if orbital_on(cfg, env):
            self._surge, u_hull = self._wave_surge(dt, env, mu_w, cfg, seed=not self._surging)
            self._surging = True
        else:
            self._surge, u_hull = 0.0, 0.0
            self._surge_y = [0.0, 0.0]
            self._surging = False

        # Ground velocity with the previous leeway (heel depends on it via apparent wind).
        ground = self._ground_velocity(current)
        aws, awa = self._apparent(wind_ground, ground)

        # Heel from the static table (sailing only), smoothed so tacks don't jump.
        heel_target = 0.0
        if not motoring:
            heel_deg = self.heel_table.heel_deg(ms_to_kn(aws), math.degrees(awa))
            heel_target = -math.copysign(math.radians(heel_deg), awa)  # wind from stbd -> heel to port
        self._heel += (heel_target - self._heel) * min(dt / HEEL_TIME_CONSTANT, 1.0)
        heel_rate = (heel_target - self._heel) / HEEL_TIME_CONSTANT
        self._leeway = leeway(self._heel, self._stw, cfg.boat.leeway_k, motoring)

        ground = self._ground_velocity(current)
        sog, cog = geo.polar(ground)
        self._sog, self._cog = sog, cog
        self._lat, self._lon = geo.step_position(self._lat, self._lon, ground[0] * dt, ground[1] * dt)
        self._log_total += self._stw * dt
        self._log_trip += self._stw * dt

        yaw = self._yaw
        damping = sail_roll_damping(aws, motoring, cfg.boat.sail_roll_damping, cfg.boat.sail_damping_aws_ref)
        roll = max(-MAX_ROLL, min(MAX_ROLL, self._heel + damping * roll_w))
        # Time derivative of the roll at this instant (heel and waves exact, the slowly varying sail
        # damping from the last step); the masthead wind sensor moves with it.
        damping_rate = 0.0 if self._last_damping is None else (damping - self._last_damping) / dt
        self._last_damping = damping
        roll_rate = 0.0 if abs(roll) == MAX_ROLL else heel_rate + damping * roll_w_rate + damping_rate * roll_w
        heading_wave = geo.wrap_2pi(self._heading + yaw)
        rot = 0.0 if self._last_heading_wave is None else geo.wrap_pi(heading_wave - self._last_heading_wave) / dt
        self._last_heading_wave = heading_wave
        rudder = rate / (0.15 * max(self._stw, 1.0)) - 1.5 * yaw
        rudder = max(-MAX_RUDDER, min(MAX_RUDDER, rudder))

        return BoatState(
            lat=self._lat,
            lon=self._lon,
            heading=self._heading,
            heading_wave=heading_wave,
            rot=rot,
            ctw=geo.wrap_2pi(heading_wave + self._leeway),
            stw=self._stw,
            target_stw=target,
            leeway=self._leeway,
            heel=self._heel,
            roll=roll,
            pitch=pitch,
            rudder=rudder,
            sog=sog,
            cog=cog,
            aws=aws,
            awa=awa,
            wws=wws,
            wwd=wwd,
            motoring=motoring,
            rpm=ap.rpm if motoring else 0.0,
            log_total=self._log_total,
            log_trip=self._log_trip,
            wave_phase=self._wave_phase,
            wave_mu=self._wave_mu,
            yaw_wave=yaw,
            roll_rate=roll_rate,
            pitch_rate=pitch_rate,
            mu_w=mu_w,
            wave_surge=self._surge,
            orbital_fwd=u_hull,
        )

    def _target_heading(self, cfg: Scenario, wwd: float) -> float:
        ap = cfg.autopilot
        if ap.mode == "twa":
            return geo.wrap_2pi(wwd - math.radians(ap.twa))
        return math.radians(ap.heading % 360.0)

    def _ground_velocity(self, current: tuple[float, float]) -> tuple[float, float]:
        water = geo.vector(self._stw + self._surge, self._heading + self._yaw + self._leeway)
        return geo.add(water, current)

    def _apparent(self, wind_ground, ground) -> tuple[float, float]:
        """Apparent wind: air velocity relative to the boat, angle relative to the heading."""
        aws, from_dir = geo.wind_from_polar(geo.sub(wind_ground, ground))
        return aws, geo.wrap_pi(from_dir - self._heading - self._yaw)

    def _waves(
        self, dt: float, env: EnvironmentState, sog: float, cog: float
    ) -> tuple[float, float, float, float, float]:
        """Returns the wave components (roll, pitch, yaw) in rad and the roll and pitch rates in rad/s;
        roll is added to the heel.

        Roll and pitch follow the slope of the sea surface at the boat. In boat coordinates
        (x forward, y starboard) the surface is
            η = A·[cos(p − k·d·r) + (irr/f)·cos(f·p + 0.7 − f·k·d·r)],  A = H/2, f = 1.6,
        with d = (−cos μ, −sin μ) the direction the waves travel. Its slope at the boat is
        tan α·S(p)·d with tan α = πH/λ and S(p) = sin p + irr·sin(f·p + 0.7), so bow-up pitch is
        −α·cos μ·S(p) and starboard-down roll is α·sin μ·S(p). The 3D view draws the same surface.
        """
        if env.wave_height <= 0:
            self._last_mu = None
            self._omega_e_slow = None
            return 0.0, 0.0, 0.0, 0.0, 0.0
        omega = 2 * math.pi / env.wave_period
        k = 2 * math.pi / env.wave_length
        mu = geo.wrap_pi(env.wave_dir - cog)  # 0 = head seas
        self._wave_mu = mu
        mu_rate = 0.0 if self._last_mu is None else geo.wrap_pi(mu - self._last_mu) / dt  # course changes
        self._last_mu = mu
        omega_e_signed = omega + k * sog * math.cos(mu)  # < 0: the boat overtakes the waves
        omega_e = abs(omega_e_signed)
        if self._omega_e_slow is None:
            self._omega_e_slow = omega_e_signed
        else:
            self._omega_e_slow += (omega_e_signed - self._omega_e_slow) * min(dt / ENCOUNTER_SMOOTHING, 1.0)
        self._wave_phase = (self._wave_phase + omega_e * dt) % (2 * math.pi * 1000)
        slope = math.atan(math.pi * env.wave_height / env.wave_length)
        irr = env.wave_irregularity
        p = self._wave_phase
        s = math.sin(p) + irr * math.sin(SECONDARY_FREQ * p + 0.7)
        s_rate = omega_e * (math.cos(p) + irr * SECONDARY_FREQ * math.cos(SECONDARY_FREQ * p + 0.7))
        roll_w = ROLL_FACTOR * slope * math.sin(mu) * s
        pitch_w = -PITCH_FACTOR * slope * math.cos(mu) * s
        yaw_w = slope * YAW_FACTOR * abs(math.sin(2 * mu)) * math.sin(p + 1.0)
        roll_rate = ROLL_FACTOR * slope * (math.sin(mu) * s_rate + math.cos(mu) * s * mu_rate)
        pitch_rate = -PITCH_FACTOR * slope * (math.cos(mu) * s_rate - math.sin(mu) * s * mu_rate)
        if abs(pitch_w) > MAX_PITCH:
            pitch_rate = 0.0
        return roll_w, max(-MAX_PITCH, min(MAX_PITCH, pitch_w)), yaw_w, roll_rate, pitch_rate

    def _wave_surge(
        self, dt: float, env: EnvironmentState, mu_w: float, cfg: Scenario, seed: bool
    ) -> tuple[float, float]:
        """Returns (w, u): the hull's wave surge and the orbital velocity at the hull, both along the
        course through water in m/s.

        Per wave component w = κ′·u + y with dy/dt = ((1 − κ′)·u − y)/τ: the wave pressure force
        (Froude–Krylov, ∝ the water acceleration ω·u, integrated at the encounter frequency) and the
        drag pull with the boat's speed time constant τ. κ′ = s·sinc(k·LWL·|cos μ_w|/2)·ω/ω_e with
        the signed, smoothed ω_e (|ω/ω_e| ≤ 2). `seed` starts y so that w is continuous (0) when the
        effect is switched on.
        """
        a = min(dt / max(cfg.boat.stw_time_constant_s, 0.1), 1.0)
        along = -math.cos(mu_w)
        surge = u_total = 0.0
        for i, (u_surface, k, omega, encounter_factor) in enumerate(orbital_components(env, self._wave_phase)):
            u = u_surface * math.exp(-k * HULL_DEPTH) * along
            x = k * cfg.boat.lwl * abs(along) / 2
            length = math.sin(x) / x if x > 1e-9 else 1.0
            kp = cfg.boat.wave_surge_factor * length * surge_ratio(omega, encounter_factor * self._omega_e_slow)
            if seed:
                self._surge_y[i] = -kp * u
            self._surge_y[i] += ((1.0 - kp) * u - self._surge_y[i]) * a
            surge += kp * u + self._surge_y[i]
            u_total += u
        return surge, u_total


def orbital_on(cfg: Scenario, env: EnvironmentState) -> bool:
    return cfg.waves.orbital and env.wave_height > 0


def surge_ratio(omega: float, omega_e: float) -> float:
    """ω/ω_e of the wave pressure response, limited to ±SURGE_RATIO_CAP. ω_e is signed: negative when
    the boat overtakes the waves, which reverses the response."""
    if abs(omega_e) * SURGE_RATIO_CAP <= omega:
        return math.copysign(SURGE_RATIO_CAP, omega_e)
    return omega / omega_e


def orbital_components(env: EnvironmentState, phase: float) -> tuple[tuple[float, float, float, float], ...]:
    """The wave components as (u, k, ω, ω_e factor): the orbital velocity at the surface in the wave
    travel direction (A·ω·cos phase), the wavenumber, the frequency and the factor on the encounter
    frequency. The secondary has wavenumber f·k, phase f·p + 0.7, encounter f·ω_e and its amplitude
    from its deep-water frequency √f·ω."""
    f = SECONDARY_FREQ
    a = env.wave_height / 2
    k = 2 * math.pi / env.wave_length
    omega = 2 * math.pi / env.wave_period
    a2, omega2 = env.wave_irregularity / f * a, math.sqrt(f) * omega
    return (
        (a * omega * math.cos(phase), k, omega, 1.0),
        (a2 * omega2 * math.cos(f * phase + 0.7), f * k, omega2, f),
    )


def orbital_fwd(env: EnvironmentState, phase: float, mu_w: float, depth: float) -> float:
    """Orbital water velocity (m/s) at `depth` along the course through water, forward +.

    The water moves in the wave travel direction under a crest; μ_w is the direction the waves come
    from relative to the course through water, so head seas give −u (the water moves aft).
    """
    along = -math.cos(mu_w)
    return sum(u * math.exp(-k * depth) for u, k, _, _ in orbital_components(env, phase)) * along


def leeway(heel: float, stw: float, k: float, motoring: bool) -> float:
    """Leeway (rad) from heel (rad, signed) and STW (m/s): λ = K·heel/STW² in degrees and knots.

    The boat slips to leeward, which has the same sign as the heel.
    """
    stw_kn = stw / KNOT
    if motoring or stw_kn < 1.0:
        return 0.0
    deg = k * math.degrees(heel) / (stw_kn * stw_kn)
    return math.radians(max(-MAX_LEEWAY, min(MAX_LEEWAY, deg)))


def sail_roll_damping(aws: float, motoring: bool, f_min: float, aws_ref_kn: float) -> float:
    """Factor (f_min..1) applied to the wave-induced roll: loaded sails resist rolling.

    Sail load grows with apparent wind speed up to `aws_ref_kn`; with the engine on the sails are
    down and the roll is undamped.
    """
    if motoring:
        return 1.0
    load = min(ms_to_kn(aws) / max(aws_ref_kn, 0.1), 1.0)
    f_min = max(0.0, min(f_min, 1.0))
    return 1.0 - (1.0 - f_min) * load
