"""Wind over ground: mean direction with a slow random walk, oscillation, lulls and gusts."""

from __future__ import annotations

import math
import random

from n2k_sim.config import Wind
from n2k_sim.units import kn_to_ms

MAX_TWS = kn_to_ms(70.0)
LULL_PERIOD = 180.0  # s
SECONDARY_RATIO = 0.37  # period ratio of the irregular secondary oscillation


def gust_shape(x: float) -> float:
    """Smooth gust envelope over x = 0..1: quick rise (first third), slower decay, 0 outside."""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    if x < 1.0 / 3.0:
        return math.sin(x * 1.5 * math.pi) ** 2
    return math.cos((x - 1.0 / 3.0) * 0.75 * math.pi) ** 2


class WindModel:
    """Stateful wind model; holds the random walk and the scheduled gusts."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._walk = 0.0  # deg
        self._gusts: list[float] = []  # start times
        self._next_gust: float | None = None
        self._phase = rng.uniform(0, 2 * math.pi)

    def trigger_gust(self, t: float) -> None:
        self._gusts.append(t)

    def step(self, t: float, dt: float, cfg: Wind) -> tuple[float, float, float]:
        """Returns (direction from in rad, speed in m/s, gust factor)."""
        if cfg.fixed:
            return math.radians(cfg.twd % 360.0), kn_to_ms(max(cfg.tws, 0.0)), 0.0

        self._advance_walk(dt, cfg)
        self._schedule_gusts(t, cfg)

        period = max(cfg.osc_period_min, 0.1) * 60.0
        direction = (
            cfg.twd
            + self._walk
            + cfg.osc_amplitude * math.sin(2 * math.pi * t / period)
            + 0.3 * cfg.osc_amplitude * math.sin(2 * math.pi * t / (SECONDARY_RATIO * period) + self._phase)
        )
        duration = max(cfg.gust_duration_s, 1.0)
        gust = sum(gust_shape((t - start) / duration) for start in self._gusts)
        self._gusts = [s for s in self._gusts if t - s < duration]

        lull = cfg.lull_depth_pct / 100.0 * 0.5 * (1 + math.sin(2 * math.pi * t / LULL_PERIOD))
        speed = cfg.tws * (1 - lull) * (1 + cfg.gust_strength_pct / 100.0 * gust)
        direction += cfg.gust_veer * gust
        speed = min(max(kn_to_ms(speed), 0.0), MAX_TWS)
        return math.radians(direction % 360.0), speed, gust

    def _advance_walk(self, dt: float, cfg: Wind) -> None:
        # Bounded random walk: drifts at up to shift_rate, pulled back softly beyond ±3 amplitudes.
        rate = cfg.shift_rate / 60.0  # deg/s
        limit = 3.0 * max(cfg.osc_amplitude, 1.0)
        pull = -self._walk / limit
        self._walk += (self._rng.uniform(-1, 1) + 0.5 * pull) * rate * dt

    def _schedule_gusts(self, t: float, cfg: Wind) -> None:
        if cfg.gust_interval_s <= 0:
            self._next_gust = None
            return
        if self._next_gust is None:
            self._next_gust = t + self._rng.expovariate(1.0 / cfg.gust_interval_s)
        if t >= self._next_gust:
            self._gusts.append(t)
            self._next_gust = t + self._rng.expovariate(1.0 / cfg.gust_interval_s)
