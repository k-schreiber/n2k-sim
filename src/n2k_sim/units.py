"""Unit conversions. Internal values are SI (m, m/s, rad, K, Pa); UI values use the units below."""

from __future__ import annotations

import math

KNOT = 1852.0 / 3600.0  # m/s per knot
NAUTICAL_MILE = 1852.0  # m
ZERO_CELSIUS = 273.15  # K
HPA = 100.0  # Pa
BAR = 100000.0  # Pa


def kn_to_ms(v: float) -> float:
    return v * KNOT


def ms_to_kn(v: float) -> float:
    return v / KNOT


def deg_to_rad(v: float) -> float:
    return math.radians(v)


def rad_to_deg(v: float) -> float:
    return math.degrees(v)


def c_to_k(v: float) -> float:
    return v + ZERO_CELSIUS


def k_to_c(v: float) -> float:
    return v - ZERO_CELSIUS


# Conversion table used by the API: unit key -> (to_ui, from_ui, label).
# "deg360" wraps to 0..360, "deg180" to -180..180.
UI_UNITS: dict[str, tuple] = {
    "kn": (ms_to_kn, kn_to_ms, "kn"),
    "deg360": (lambda v: math.degrees(v) % 360.0, deg_to_rad, "°"),
    "deg180": (lambda v: (math.degrees(v) + 180.0) % 360.0 - 180.0, deg_to_rad, "°"),
    "deg": (rad_to_deg, deg_to_rad, "°"),
    "deg_per_min": (lambda v: math.degrees(v) * 60.0, lambda v: math.radians(v) / 60.0, "°/min"),
    "degc": (k_to_c, c_to_k, "°C"),
    "hpa": (lambda v: v / HPA, lambda v: v * HPA, "hPa"),
    "bar": (lambda v: v / BAR, lambda v: v * BAR, "bar"),
    "nm": (lambda v: v / NAUTICAL_MILE, lambda v: v * NAUTICAL_MILE, "nm"),
    "hours": (lambda v: v / 3600.0, lambda v: v * 3600.0, "h"),
    "m": (lambda v: v, lambda v: v, "m"),
    "pct": (lambda v: v, lambda v: v, "%"),
    "v": (lambda v: v, lambda v: v, "V"),
    "a": (lambda v: v, lambda v: v, "A"),
    "rpm": (lambda v: v, lambda v: v, "rpm"),
    "l": (lambda v: v, lambda v: v, "L"),
    "lph": (lambda v: v, lambda v: v, "L/h"),
    "s": (lambda v: v, lambda v: v, "s"),
    "min": (lambda v: v, lambda v: v, "min"),
    "latlon": (lambda v: v, lambda v: v, "°"),
    "none": (lambda v: v, lambda v: v, ""),
    "time": (lambda v: v, lambda v: v, "UTC"),
}


def to_ui(value, unit: str):
    if value is None or not isinstance(value, (int, float)):
        return value
    return UI_UNITS[unit][0](value)


def from_ui(value, unit: str):
    if value is None:
        return None
    return UI_UNITS[unit][1](float(value))
