"""Tier 2: the boat. Reads the environment (never the sensors) and produces the boat's true state.

Lean by design: first-order speed response, P-controlled autopilot, heel from a lookup table,
leeway from the classic K·heel/STW² formula and wave-driven attitude (see docs/spec/simulation.md).
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
        self._yaw = 0.0  # rad, wave-induced yaw; turns the hull and therefore its track
        self._sog = 0.0
        self._cog = 0.0
        self._last_heading_wave: float | None = None
        self._log_total = 0.0
        self._log_trip = 0.0
        self._initialised = False

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
        err = geo.wrap_pi(self._target_heading(cfg, wwd) - self._heading)
        r_max = math.radians(cfg.boat.max_turn_rate)
        rate = max(-r_max, min(r_max, KP * err))
        self._heading = geo.wrap_2pi(self._heading + rate * dt)

        # Speed: first-order lag towards polar or motor speed.
        twa_water = geo.wrap_pi(wwd - self._heading)
        if motoring:
            target = kn_to_ms(ap.rpm / 1000.0 * cfg.boat.motor_speed_per_1000rpm)
        else:
            target = kn_to_ms(self.polar.boat_speed(ms_to_kn(wws), math.degrees(twa_water)))
        tau = max(cfg.boat.stw_time_constant_s, 0.1)
        self._stw += (target - self._stw) * min(dt / tau, 1.0)

        # Wave-induced motion (encounter frequency from the previous ground track). Yaw turns the
        # whole hull, so it changes the track as well as what the compass sees.
        roll_w, pitch, self._yaw = self._waves(dt, env, self._sog, self._cog)

        # Ground velocity with the previous leeway (heel depends on it via apparent wind).
        ground = self._ground_velocity(current)
        aws, awa = self._apparent(wind_ground, ground)

        # Heel from the static table (sailing only), smoothed so tacks don't jump.
        heel_target = 0.0
        if not motoring:
            heel_deg = self.heel_table.heel_deg(ms_to_kn(aws), math.degrees(awa))
            heel_target = -math.copysign(math.radians(heel_deg), awa)  # wind from stbd -> heel to port
        self._heel += (heel_target - self._heel) * min(dt / HEEL_TIME_CONSTANT, 1.0)
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
        )

    def _target_heading(self, cfg: Scenario, wwd: float) -> float:
        ap = cfg.autopilot
        if ap.mode == "twa":
            return geo.wrap_2pi(wwd - math.radians(ap.twa))
        return math.radians(ap.heading % 360.0)

    def _ground_velocity(self, current: tuple[float, float]) -> tuple[float, float]:
        water = geo.vector(self._stw, self._heading + self._yaw + self._leeway)
        return geo.add(water, current)

    def _apparent(self, wind_ground, ground) -> tuple[float, float]:
        """Apparent wind: air velocity relative to the boat, angle relative to the heading."""
        aws, from_dir = geo.wind_from_polar(geo.sub(wind_ground, ground))
        return aws, geo.wrap_pi(from_dir - self._heading - self._yaw)

    def _waves(self, dt: float, env: EnvironmentState, sog: float, cog: float) -> tuple[float, float, float]:
        """Returns the wave components (roll, pitch, yaw) in rad; roll is added to the heel."""
        if env.wave_height <= 0:
            return 0.0, 0.0, 0.0
        omega = 2 * math.pi / env.wave_period
        k = 2 * math.pi / env.wave_length
        mu = geo.wrap_pi(env.wave_dir - cog)  # 0 = head seas
        omega_e = abs(omega + k * sog * math.cos(mu))
        self._wave_phase = (self._wave_phase + omega_e * dt) % (2 * math.pi * 1000)
        slope = math.atan(math.pi * env.wave_height / env.wave_length)
        irr = env.wave_irregularity
        p = self._wave_phase
        roll_w = slope * abs(math.sin(mu)) * ROLL_FACTOR * (math.sin(p) + irr * math.sin(SECONDARY_FREQ * p + 0.7))
        pitch_w = slope * abs(math.cos(mu)) * PITCH_FACTOR * (math.cos(p) + irr * math.sin(SECONDARY_FREQ * p + 2.1))
        yaw_w = slope * YAW_FACTOR * abs(math.sin(2 * mu)) * math.sin(p + 1.0)
        return roll_w, max(-MAX_PITCH, min(MAX_PITCH, pitch_w)), yaw_w


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
