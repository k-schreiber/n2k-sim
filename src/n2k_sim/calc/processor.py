"""The instrument processor: derives true wind, current, leeway and performance from sensor
readings only, the way a real instrument system does (see docs/spec/signals.md)."""

from __future__ import annotations

import math
from typing import Any, Mapping

from n2k_sim import geo
from n2k_sim.boat.tables import Polar
from n2k_sim.units import KNOT, k_to_c, c_to_k

ROLL_FILTER_TIME = 10.0  # s, processors average heel before using it for leeway
CURRENT_FILTER_TIME = 20.0  # s, set & drift damping (vector average), as on real instruments
MAX_LEEWAY = 10.0  # deg
MAGNUS_A, MAGNUS_B = 17.62, 243.12


class Processor:
    def __init__(self, polar: Polar):
        self.polar = polar
        self._roll: float | None = None
        self._current: tuple[float, float] | None = None  # damped (east, north) vector

    def step(self, r: Mapping[str, Any], dt: float, leeway_k: float) -> dict[str, Any]:
        out: dict[str, Any] = dict.fromkeys(
            ("heading_true", "leeway_calc", "tws", "twa", "twd", "gws", "gwa", "gwd", "current_set",
             "current_drift", "vmg_wind", "polar_speed", "performance", "dew_point")
        )
        out["dew_point"] = dew_point(r.get("air_temp"), r.get("humidity"))

        hdg_mag, var = r.get("heading_mag"), r.get("variation")
        if hdg_mag is None or var is None:
            return out
        hdg = geo.wrap_2pi(hdg_mag + var)
        out["heading_true"] = hdg

        stw, roll = r.get("stw"), r.get("roll")
        if stw is None:
            return out
        if roll is not None:
            self._roll = roll if self._roll is None else self._roll + (roll - self._roll) * min(dt / ROLL_FILTER_TIME, 1.0)
        lw = leeway(self._roll or 0.0, stw, leeway_k)
        out["leeway_calc"] = lw

        aws, awa = r.get("aws"), r.get("awa")
        if aws is not None and awa is not None:
            tws, twa = true_wind(aws, awa, stw, lw)
            out.update(tws=tws, twa=twa, twd=geo.wrap_2pi(hdg + twa), vmg_wind=stw * math.cos(twa))
            polar_speed = self.polar.boat_speed(tws / KNOT, math.degrees(twa)) * KNOT
            out["polar_speed"] = polar_speed
            out["performance"] = 100.0 * stw / polar_speed if polar_speed > 0.1 else None

        sog, cog = r.get("sog"), r.get("cog")
        if sog is not None and cog is not None:
            if aws is not None and awa is not None:
                gws, gwa = true_wind(aws, awa, sog, geo.wrap_pi(cog - hdg))
                out.update(gws=gws, gwa=gwa, gwd=geo.wrap_2pi(hdg + gwa))
            raw = geo.sub(geo.vector(sog, cog), geo.vector(stw, hdg + lw))
            if self._current is None:
                self._current = raw
            else:
                a = min(dt / CURRENT_FILTER_TIME, 1.0)
                self._current = (self._current[0] + (raw[0] - self._current[0]) * a,
                                 self._current[1] + (raw[1] - self._current[1]) * a)
            drift, set_ = geo.polar(self._current)
            out.update(current_set=set_, current_drift=drift)
        return out


def true_wind(aws: float, awa: float, speed: float, course_offset: float) -> tuple[float, float]:
    """Wind relative to a frame moving at `speed` towards heading + course_offset.

    Angles are relative to the heading. Returns (speed, angle -π..π)."""
    x = aws * math.sin(awa) - speed * math.sin(course_offset)
    y = aws * math.cos(awa) - speed * math.cos(course_offset)
    return math.hypot(x, y), math.atan2(x, y)


def leeway(roll: float, stw: float, k: float) -> float:
    """λ = K·heel/STW² (degrees, knots), signed like the heel, zero below 1 kn."""
    stw_kn = stw / KNOT
    if stw_kn < 1.0:
        return 0.0
    deg = k * math.degrees(roll) / (stw_kn * stw_kn)
    return math.radians(max(-MAX_LEEWAY, min(MAX_LEEWAY, deg)))


def dew_point(air_temp: float | None, humidity: float | None) -> float | None:
    """Magnus formula. Temperatures in K, humidity in %."""
    if air_temp is None or humidity is None or humidity <= 0:
        return None
    t = k_to_c(air_temp)
    gamma = math.log(humidity / 100.0) + MAGNUS_A * t / (MAGNUS_B + t)
    return c_to_k(MAGNUS_B * gamma / (MAGNUS_A - gamma))
