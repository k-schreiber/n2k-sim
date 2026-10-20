"""The catalogue of every signal (see docs/spec/signals.md).

Values are stored in SI units: m, m/s, rad, K, Pa, s. Exceptions: lat/lon in degrees, percentages
0..100, electrical values in V/A, engine speed in rpm, volumes in L, fuel rate in L/h, time as UNIX
epoch seconds. `ui` names the UI unit (key of units.UI_UNITS). Boat-relative angles are -π..π with
positive = starboard; bearings are 0..2π.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Layer(str, Enum):
    ENV = "env"  # tier 1/2 truth, shown in the UI, never transmitted
    SENSOR = "sensor"  # tier 3 readings
    CALC = "calc"  # instrument processor
    STATIC = "static"  # set by the user


@dataclass(frozen=True)
class SignalDef:
    name: str
    ui: str
    layer: Layer
    group: str
    label: str
    pgns: tuple[int, ...] = ()
    scalar: bool = True  # False for structured values (e.g. the satellite list)


def _s(name, ui, layer, group, label, *pgns, scalar=True):
    return SignalDef(name, ui, layer, group, label, tuple(pgns), scalar)


E, S, C, T = Layer.ENV, Layer.SENSOR, Layer.CALC, Layer.STATIC

SIGNALS: tuple[SignalDef, ...] = (
    # --- Tier 1/2 truth ---------------------------------------------------------------------
    _s("env.gwd", "deg360", E, "wind", "Ground wind direction"),
    _s("env.gws", "kn", E, "wind", "Ground wind speed"),
    _s("env.wwd", "deg360", E, "wind", "Water wind direction"),
    _s("env.wws", "kn", E, "wind", "Water wind speed"),
    _s("env.gust", "pct", E, "wind", "Gust factor"),
    _s("env.current_set", "deg360", E, "current", "Current set"),
    _s("env.current_drift", "kn", E, "current", "Current drift"),
    _s("env.wave_dir", "deg360", E, "waves", "Wave direction (from)"),
    _s("env.wave_height", "m", E, "waves", "Wave height"),
    _s("env.wave_length", "m", E, "waves", "Wavelength"),
    _s("env.wave_period", "s", E, "waves", "Wave period"),
    _s("env.depth", "m", E, "seabed", "Depth below waterline"),
    _s("boat.heading", "deg360", E, "boat", "True heading"),
    _s("boat.ctw", "deg360", E, "boat", "Course through water"),
    _s("boat.stw", "kn", E, "boat", "Speed through water"),
    _s("boat.leeway", "deg180", E, "boat", "Leeway"),
    _s("boat.heel", "deg180", E, "boat", "Heel"),
    _s("boat.awa", "deg180", E, "boat", "True apparent wind angle"),
    _s("boat.aws", "kn", E, "boat", "True apparent wind speed"),
    _s("boat.target_stw", "kn", E, "boat", "Polar target speed"),
    # --- Tier 3 sensors -----------------------------------------------------------------------
    _s("awa", "deg180", S, "wind", "Apparent wind angle", 130306),
    _s("aws", "kn", S, "wind", "Apparent wind speed", 130306),
    _s("heading_mag", "deg360", S, "compass", "Magnetic heading", 127250),
    _s("rot", "deg_per_min", S, "compass", "Rate of turn", 127251),
    _s("yaw", "deg360", S, "compass", "Yaw", 127257),
    _s("pitch", "deg180", S, "compass", "Pitch", 127257),
    _s("roll", "deg180", S, "compass", "Roll", 127257),
    _s("rudder", "deg180", S, "steering", "Rudder angle", 127245),
    _s("stw", "kn", S, "log", "Speed through water", 128259),
    _s("log_total", "nm", S, "log", "Total log", 128275),
    _s("log_trip", "nm", S, "log", "Trip log", 128275),
    _s("depth", "m", S, "depth", "Depth below transducer", 128267),
    _s("depth_offset", "m", S, "depth", "Transducer offset", 128267),
    _s("lat", "latlon", S, "gps", "Latitude", 129025, 129029),
    _s("lon", "latlon", S, "gps", "Longitude", 129025, 129029),
    _s("cog", "deg360", S, "gps", "Course over ground", 129026),
    _s("sog", "kn", S, "gps", "Speed over ground", 129026),
    _s("gnss_time", "time", S, "gps", "GNSS time", 126992, 129029, 129033),
    _s("local_offset", "min", S, "gps", "Local time offset", 129033),
    _s("variation", "deg180", S, "gps", "Magnetic variation (E+)", 127258),
    _s("altitude", "m", S, "gps", "Altitude", 129029),
    _s("geoidal_separation", "m", S, "gps", "Geoidal separation", 129029),
    _s("gnss_type", "none", S, "gps", "GNSS type (0 GPS)", 129029),
    _s("fix_method", "none", S, "gps", "Fix method (1 GNSS fix)", 129029),
    _s("fix_mode", "none", S, "gps", "Fix mode (2 = 3D)", 129539),
    _s("sats_used", "none", S, "gps", "Satellites used", 129029),
    _s("sats_in_view", "none", S, "gps", "Satellites in view", 129540),
    _s("satellites", "none", S, "gps", "Satellite list", 129540, scalar=False),
    _s("hdop", "none", S, "gps", "HDOP", 129029, 129539),
    _s("vdop", "none", S, "gps", "VDOP", 129539),
    _s("pdop", "none", S, "gps", "PDOP", 129029),
    _s("tdop", "none", S, "gps", "TDOP", 129539),
    # --- Instrument processor -----------------------------------------------------------------
    _s("heading_true", "deg360", C, "processor", "True heading"),
    _s("leeway_calc", "deg180", C, "processor", "Leeway (calculated)"),
    _s("tws", "kn", C, "processor", "True wind speed (water)", 130306),
    _s("twa", "deg180", C, "processor", "True wind angle (water)", 130306),
    _s("twd", "deg360", C, "processor", "True wind direction (water)"),
    _s("gws", "kn", C, "processor", "Ground wind speed", 130306),
    _s("gwa", "deg180", C, "processor", "Ground wind angle", 130306),
    _s("gwd", "deg360", C, "processor", "Ground wind direction", 130306),
    _s("current_set", "deg360", C, "processor", "Current set", 129291),
    _s("current_drift", "kn", C, "processor", "Current drift", 129291),
    _s("vmg_wind", "kn", C, "processor", "VMG to wind"),
    _s("polar_speed", "kn", C, "processor", "Polar target speed"),
    _s("performance", "pct", C, "processor", "Polar performance"),
    _s("dew_point", "degc", C, "processor", "Dew point", 130316),
    # --- Static -------------------------------------------------------------------------------
    _s("water_temp", "degc", T, "meteo", "Water temperature", 130312, 130310),
    _s("air_temp", "degc", T, "meteo", "Air temperature", 130311, 130310),
    _s("pressure", "hpa", T, "meteo", "Air pressure", 130311, 130314, 130310),
    _s("humidity", "pct", T, "meteo", "Relative humidity", 130311, 130313),
    _s("cabin_temp", "degc", T, "meteo", "Cabin temperature", 130312),
    _s("engine.rpm", "rpm", T, "engine", "Engine speed", 127488),
    _s("engine.oil_pressure", "bar", T, "engine", "Oil pressure", 127489),
    _s("engine.oil_temp", "degc", T, "engine", "Oil temperature", 127489),
    _s("engine.coolant_temp", "degc", T, "engine", "Coolant temperature", 127489),
    _s("engine.alternator_v", "v", T, "engine", "Alternator voltage", 127489),
    _s("engine.fuel_rate", "lph", T, "engine", "Fuel rate", 127489),
    _s("engine.hours", "hours", T, "engine", "Engine hours", 127489),
    _s("engine.load", "pct", T, "engine", "Engine load", 127489),
    _s("tank.fuel.level", "pct", T, "tanks", "Fuel level", 127505),
    _s("tank.fuel.capacity", "l", T, "tanks", "Fuel capacity", 127505),
    _s("tank.fresh_water1.level", "pct", T, "tanks", "Fresh water 1 level", 127505),
    _s("tank.fresh_water1.capacity", "l", T, "tanks", "Fresh water 1 capacity", 127505),
    _s("tank.fresh_water2.level", "pct", T, "tanks", "Fresh water 2 level", 127505),
    _s("tank.fresh_water2.capacity", "l", T, "tanks", "Fresh water 2 capacity", 127505),
    _s("tank.black_water.level", "pct", T, "tanks", "Black water level", 127505),
    _s("tank.black_water.capacity", "l", T, "tanks", "Black water capacity", 127505),
    _s("battery.house.voltage", "v", T, "batteries", "House battery voltage", 127508),
    _s("battery.house.current", "a", T, "batteries", "House battery current", 127508),
    _s("battery.house.temp", "degc", T, "batteries", "House battery temperature", 127508),
    _s("battery.engine.voltage", "v", T, "batteries", "Engine battery voltage", 127508),
    _s("battery.engine.current", "a", T, "batteries", "Engine battery current", 127508),
    _s("battery.engine.temp", "degc", T, "batteries", "Engine battery temperature", 127508),
)

BY_NAME: dict[str, SignalDef] = {s.name: s for s in SIGNALS}

# Tank and battery instances: (signal prefix, N2K instance, fluid type for 127505).
# Instances are unique across all tanks, as the NMEA2000 library recommends.
TANKS: tuple[tuple[str, int, int], ...] = (
    ("tank.fuel", 0, 0),
    ("tank.fresh_water1", 1, 1),
    ("tank.fresh_water2", 2, 1),
    ("tank.black_water", 3, 5),
)
BATTERIES: tuple[tuple[str, int], ...] = (("battery.house", 0), ("battery.engine", 1))
