"""Angle and vector helpers. Bearings are radians clockwise from north; vectors are (east, north)."""

from __future__ import annotations

import math

TWO_PI = 2.0 * math.pi
EARTH_RADIUS = 6371000.0  # m


def wrap_2pi(a: float) -> float:
    """Wraps an angle to 0..2π."""
    return a % TWO_PI


def wrap_pi(a: float) -> float:
    """Wraps an angle to -π..π."""
    return (a + math.pi) % TWO_PI - math.pi


def vector(speed: float, bearing: float) -> tuple[float, float]:
    """Returns the (east, north) vector of a speed moving towards a bearing."""
    return speed * math.sin(bearing), speed * math.cos(bearing)


def polar(v: tuple[float, float]) -> tuple[float, float]:
    """Returns (magnitude, bearing 0..2π) of an (east, north) vector."""
    east, north = v
    return math.hypot(east, north), wrap_2pi(math.atan2(east, north))


def add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] + b[0], a[1] + b[1]


def sub(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] - b[0], a[1] - b[1]


def step_position(lat: float, lon: float, east_m: float, north_m: float) -> tuple[float, float]:
    """Moves a position (degrees) by a small displacement in metres (local flat-earth step)."""
    dlat = math.degrees(north_m / EARTH_RADIUS)
    dlon = math.degrees(east_m / (EARTH_RADIUS * math.cos(math.radians(lat))))
    lon = (lon + dlon + 180.0) % 360.0 - 180.0
    return lat + dlat, lon


def wind_from_vector(speed: float, from_dir: float) -> tuple[float, float]:
    """Returns the velocity vector (east, north) of wind blowing FROM a direction."""
    return vector(speed, from_dir + math.pi)


def wind_from_polar(v: tuple[float, float]) -> tuple[float, float]:
    """Returns (speed, direction it blows FROM) of a wind velocity vector."""
    speed, to_dir = polar(v)
    return speed, wrap_2pi(to_dir + math.pi)


def bilinear(xs: list[float], ys: list[float], table: list[list[float]], x: float, y: float) -> float:
    """Interpolates table[row=y index][col=x index], clamping x and y to the table edges."""

    def locate(axis: list[float], v: float) -> tuple[int, float]:
        if v <= axis[0]:
            return 0, 0.0
        if v >= axis[-1]:
            return len(axis) - 2, 1.0
        for i in range(len(axis) - 1):
            if axis[i] <= v <= axis[i + 1]:
                return i, (v - axis[i]) / (axis[i + 1] - axis[i])
        return len(axis) - 2, 1.0

    if len(xs) == 1 and len(ys) == 1:
        return table[0][0]
    xi, xf = locate(xs, x) if len(xs) > 1 else (0, 0.0)
    yi, yf = locate(ys, y) if len(ys) > 1 else (0, 0.0)
    x1 = min(xi + 1, len(xs) - 1)
    y1 = min(yi + 1, len(ys) - 1)
    top = table[yi][xi] * (1 - xf) + table[yi][x1] * xf
    bottom = table[y1][xi] * (1 - xf) + table[y1][x1] * xf
    return top * (1 - yf) + bottom * yf
