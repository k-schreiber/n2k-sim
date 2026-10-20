"""Tier 3: noise-free sensors. Each device is a pure function of the environment, the boat and the
scenario's static values, returning the signals that kind of device measures (SI units)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from n2k_sim import geo
from n2k_sim.boat.model import BoatState
from n2k_sim.config import Scenario
from n2k_sim.environment.state import EnvironmentState
from n2k_sim.signals.catalogue import BY_NAME, Layer
from n2k_sim.units import from_ui

Readings = dict[str, Any]


@dataclass(frozen=True)
class SensorInput:
    env: EnvironmentState
    boat: BoatState
    cfg: Scenario
    utc: float  # wall clock, UNIX epoch seconds


@dataclass(frozen=True)
class DeviceSpec:
    name: str
    read: Callable[[SensorInput], Readings]


def static_value(cfg: Scenario, name: str) -> float | None:
    """A static signal from the scenario, converted from UI units to SI."""
    value = cfg.static.get(name)
    return None if value is None else from_ui(value, BY_NAME[name].ui)


def gps(s: SensorInput) -> Readings:
    g = s.cfg.gps
    return {
        "lat": s.boat.lat,
        "lon": s.boat.lon,
        "cog": s.boat.cog,
        "sog": s.boat.sog,
        "gnss_time": s.utc,
        "local_offset": g.local_offset_min,
        "variation": math.radians(g.variation),
        "altitude": g.altitude,
        "geoidal_separation": g.geoidal_separation,
        "gnss_type": 0,
        "fix_method": 1,
        "fix_mode": 2,
        "sats_used": min(g.sats_used, g.sats_in_view),
        "sats_in_view": g.sats_in_view,
        "satellites": satellites(s.env.t, g.sats_in_view, g.sats_used),
        "hdop": g.hdop,
        "vdop": g.vdop,
        "pdop": g.pdop,
        "tdop": g.tdop,
    }


def satellites(t: float, in_view: int, used: int) -> list[tuple[int, float, float, float, int]]:
    """A plausible, slowly moving sky: (PRN, elevation rad, azimuth rad, SNR dB, status)."""
    sats = []
    for i in range(in_view):
        prn = 2 + 3 * i % 31
        azimuth = geo.wrap_2pi(math.radians(i * 360.0 / max(in_view, 1) + t / 240.0))
        elevation = math.radians(10 + (i * 37) % 75 + 5 * math.sin(t / 600.0 + i))
        snr = 30.0 + math.degrees(elevation) * 0.2
        status = 2 if i < used else 1  # used / tracked
        sats.append((prn, elevation, azimuth, snr, status))
    return sats


def compass(s: SensorInput) -> Readings:
    """Fluxgate compass with attitude sensor: magnetic heading, rate of turn, yaw/pitch/roll."""
    variation = math.radians(s.cfg.gps.variation)
    return {
        "heading_mag": geo.wrap_2pi(s.boat.heading_wave - variation),
        "rot": s.boat.rot,
        "yaw": s.boat.heading_wave,
        "pitch": s.boat.pitch,
        "roll": s.boat.roll,
    }


def wind_sensor(s: SensorInput) -> Readings:
    return {"awa": s.boat.awa, "aws": s.boat.aws}


def speed_log(s: SensorInput) -> Readings:
    return {
        "stw": s.boat.stw,
        "log_total": s.boat.log_total,
        "log_trip": s.boat.log_trip,
        "water_temp": static_value(s.cfg, "water_temp"),
    }


def depth_sounder(s: SensorInput) -> Readings:
    bed = s.cfg.seabed
    return {
        "depth": max(s.env.depth - bed.transducer_depth, 0.0),
        # Offset from the transducer: + = to waterline, - = to keel. Report depth below keel.
        "depth_offset": -(bed.keel_depth - bed.transducer_depth),
    }


def rudder(s: SensorInput) -> Readings:
    return {"rudder": s.boat.rudder}


ENGINE_VALUES = (
    "engine.oil_pressure",
    "engine.oil_temp",
    "engine.coolant_temp",
    "engine.alternator_v",
    "engine.fuel_rate",
    "engine.hours",
    "engine.load",
)


def engine(s: SensorInput) -> Readings:
    """Engine interface: values only while the engine runs (RPM > 0)."""
    rpm = s.boat.rpm if s.boat.motoring else (static_value(s.cfg, "engine.rpm") or 0.0)
    running = rpm > 0
    readings: Readings = {"engine.rpm": rpm if running else None}
    for name in ENGINE_VALUES:
        readings[name] = static_value(s.cfg, name) if running else None
    return readings


def static_group(prefixes: tuple[str, ...]) -> Callable[[SensorInput], Readings]:
    names = [d.name for d in BY_NAME.values() if d.layer is Layer.STATIC and d.name.startswith(prefixes)]

    def read(s: SensorInput) -> Readings:
        return {name: static_value(s.cfg, name) for name in names}

    return read


DEVICES: tuple[DeviceSpec, ...] = (
    DeviceSpec("gps", gps),
    DeviceSpec("compass", compass),
    DeviceSpec("wind_sensor", wind_sensor),
    DeviceSpec("speed_log", speed_log),
    DeviceSpec("depth_sounder", depth_sounder),
    DeviceSpec("rudder", rudder),
    DeviceSpec("engine", engine),
    DeviceSpec("tanks", static_group(("tank.",))),
    DeviceSpec("battery", static_group(("battery.",))),
    DeviceSpec("weather", static_group(("air_temp", "pressure", "humidity", "cabin_temp"))),
)


def read_all(s: SensorInput) -> Readings:
    readings: Readings = {}
    for device in DEVICES:
        readings.update(device.read(s))
    return readings
