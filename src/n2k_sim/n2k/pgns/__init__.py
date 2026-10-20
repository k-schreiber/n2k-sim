"""PGN encoders and the default transmission schedule."""

from __future__ import annotations

from ..types import PgnSpec
from . import battery, compass, engine, environment, gps, log, processor, steering, system, tanks, wind


def _p(pgn, name, interval, prio, enc, sensor, fast=False, enabled=True, key=""):
    return PgnSpec(pgn, name, interval, prio, enc, fast, sensor, enabled, key)


def default_pgns() -> list[PgnSpec]:
    """The full default schedule (60928 is sent by the gateway itself)."""
    return [
        _p(126992, "System Time", 1.0, 3, system.encode_126992, "gps"),
        _p(127245, "Rudder", 0.1, 2, steering.encode_127245, "rudder"),
        _p(127250, "Vessel Heading", 0.1, 2, compass.encode_127250, "compass"),
        _p(127251, "Rate of Turn", 0.1, 2, compass.encode_127251, "compass"),
        _p(127257, "Attitude", 0.1, 3, compass.encode_127257, "compass"),
        _p(127258, "Magnetic Variation", 1.0, 6, gps.encode_127258, "gps"),
        _p(127488, "Engine Rapid", 0.1, 2, engine.encode_127488, "engine"),
        _p(127489, "Engine Dynamic", 0.5, 2, engine.encode_127489, "engine", fast=True),
        _p(127505, "Fluid Level", 2.5, 6, tanks.encode_127505, "tanks"),
        _p(127508, "Battery Status", 1.5, 6, battery.encode_127508, "battery"),
        _p(128259, "Speed", 1.0, 2, log.encode_128259, "speed_log"),
        _p(128267, "Water Depth", 1.0, 3, log.encode_128267, "depth_sounder"),
        _p(128275, "Distance Log", 1.0, 6, log.encode_128275, "speed_log", fast=True),
        _p(129025, "Position Rapid", 0.1, 2, gps.encode_129025, "gps"),
        _p(129026, "COG & SOG Rapid", 0.25, 2, gps.encode_129026, "gps"),
        _p(129029, "GNSS Position", 1.0, 3, gps.encode_129029, "gps", fast=True),
        _p(129033, "Time & Date", 1.0, 3, system.encode_129033, "gps"),
        _p(129291, "Set & Drift", 1.0, 3, processor.encode_129291, "processor"),
        _p(129539, "GNSS DOPs", 1.0, 6, gps.encode_129539, "gps"),
        _p(129540, "GNSS Satellites in View", 1.0, 6, gps.encode_129540, "gps", fast=True),
        _p(130306, "Wind (apparent)", 0.1, 2, wind.encode_apparent, "wind_sensor", key="130306.apparent"),
        _p(130306, "Wind (true, water referenced)", 1.0, 2, wind.encode_water, "processor", key="130306.water"),
        _p(130306, "Wind (ground, boat referenced)", 1.0, 2, wind.encode_ground_boat, "processor",
           key="130306.ground_boat"),
        _p(130306, "Wind (ground, north referenced)", 1.0, 2, wind.encode_ground, "processor",
           key="130306.ground"),
        _p(130310, "Environmental (obsolete)", 0.5, 5, environment.encode_130310, "weather", enabled=False),
        _p(130311, "Environmental", 0.5, 5, environment.encode_130311, "weather"),
        _p(130312, "Temperature", 2.0, 5, environment.encode_130312, "weather"),
        _p(130313, "Humidity", 2.0, 5, environment.encode_130313, "weather"),
        _p(130314, "Actual Pressure", 2.0, 5, environment.encode_130314, "weather"),
        _p(130316, "Temperature Extended (dew point)", 2.0, 5, environment.encode_130316, "processor"),
    ]
