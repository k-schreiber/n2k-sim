"""One simulation tick: tier 1 → tier 2 → tier 3 → processor → overrides → signal snapshot."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from n2k_sim import geo
from n2k_sim.boat.model import Boat, BoatState
from n2k_sim.boat.tables import HeelTable, Polar
from n2k_sim.calc.processor import Processor
from n2k_sim.config import DATA_DIR, Scenario
from n2k_sim.environment.model import Environment
from n2k_sim.environment.state import EnvironmentState
from n2k_sim.sensors.devices import SensorInput, read_all
from n2k_sim.signals.catalogue import BY_NAME, Layer
from n2k_sim.units import from_ui

POLAR_DIR = DATA_DIR / "polars"
HEEL_TABLE = DATA_DIR / "heel_table.json"


@dataclass(frozen=True)
class Snapshot:
    t: float  # simulation time, s
    utc: float  # wall clock of the tick
    values: dict[str, Any]  # simulated values (SI)
    sent: dict[str, Any]  # values after transmit-only overrides (SI)


def truth_signals(env: EnvironmentState, boat: BoatState) -> dict[str, Any]:
    return {
        "env.gwd": env.wind_dir,
        "env.gws": env.wind_speed,
        "env.wwd": boat.wwd,
        "env.wws": boat.wws,
        "env.gust": 100.0 * env.gust,
        "env.current_set": env.current_set,
        "env.current_drift": env.current_drift,
        "env.wave_dir": env.wave_dir,
        "env.wave_height": env.wave_height,
        "env.wave_length": env.wave_length,
        "env.wave_period": env.wave_period,
        "env.depth": env.depth,
        "boat.heading": boat.heading,
        "boat.ctw": boat.ctw,
        "boat.stw": boat.stw,
        "boat.leeway": boat.leeway,
        "boat.heel": boat.heel,
        "boat.awa": boat.awa,
        "boat.aws": boat.aws,
        "boat.target_stw": boat.target_stw,
    }


def apply_overrides(values: dict[str, Any], overrides: dict[str, float]) -> dict[str, Any]:
    sent = dict(values)
    for name, ui_value in overrides.items():
        sig = BY_NAME.get(name)
        if sig is None or sig.layer is Layer.ENV or not sig.scalar:
            continue
        value = from_ui(ui_value, sig.ui)
        if sig.ui in ("deg360",):
            value = geo.wrap_2pi(value)
        sent[name] = value
    return sent


class Simulation:
    def __init__(self, scenario: Scenario, clock: Callable[[], float] = time.time):
        self.scenario = scenario
        self.clock = clock
        self.polar = Polar.load(POLAR_DIR / scenario.boat.polar_file)
        self.heel_table = HeelTable.load(HEEL_TABLE)
        self.reset()

    def reset(self) -> None:
        self.t = 0.0
        self.env = Environment(self.scenario.seed)
        self.boat = Boat(self.scenario, self.polar, self.heel_table)
        self.processor = Processor(self.polar)
        self.snapshot: Snapshot | None = None

    def set_polar(self, polar: Polar) -> None:
        self.polar = polar
        self.boat.polar = polar
        self.processor.polar = polar

    def step(self, dt: float) -> Snapshot:
        cfg = self.scenario
        self.t += dt
        utc = self.clock()
        env = self.env.step(self.t, dt, cfg)
        boat = self.boat.step(self.t, dt, env, cfg)
        self.env_state, self.boat_state = env, boat
        readings = read_all(SensorInput(env, boat, cfg, utc))
        calc = self.processor.step(readings, dt, cfg.processor.leeway_k)
        values = {**truth_signals(env, boat), **readings, **calc}
        self.snapshot = Snapshot(self.t, utc, values, apply_overrides(values, cfg.overrides))
        return self.snapshot


def polar_files() -> list[str]:
    return sorted(p.name for p in POLAR_DIR.glob("*.pol"))


def load_polar_file(name: str) -> Polar:
    path = (POLAR_DIR / Path(name).name).resolve()
    if not path.is_file():
        raise ValueError(f"unknown polar {name}")
    return Polar.load(path)


