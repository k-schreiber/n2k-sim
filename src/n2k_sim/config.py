"""Scenario configuration. Stored and exchanged in human units (knots, degrees, metres, °C, …) so
scenario files and the UI stay readable; models convert to SI when they read it."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
G = 9.81  # m/s²


class Wind(BaseModel):
    fixed: bool = False  # True: constant twd/tws, no oscillation, shifts or gusts
    twd: float = 300.0  # deg, mean direction the wind comes from
    tws: float = 12.0  # kn, mean speed
    osc_amplitude: float = 8.0  # deg
    osc_period_min: float = 6.0
    shift_rate: float = 0.5  # deg/min, max slow random-walk rate (0 = off)
    gust_interval_s: float = 90.0  # mean time between gusts (0 = no gusts)
    gust_strength_pct: float = 35.0
    gust_duration_s: float = 20.0
    gust_veer: float = 5.0  # deg
    lull_depth_pct: float = 10.0


class Current(BaseModel):
    fixed: bool = True  # True: constant; False: tidal variation of the drift
    set: float = 135.0  # deg, direction the current flows to
    drift: float = 0.5  # kn
    tidal_amplitude_pct: float = 50.0
    tidal_period_h: float = 12.42


class Waves(BaseModel):
    enabled: bool = True
    direction: float = 290.0  # deg, waves come from
    height: float = 1.0  # m, significant wave height
    period: float = 5.0  # s; wavelength follows from deep-water dispersion
    irregularity: float = 0.2

    @model_validator(mode="before")
    @classmethod
    def _length_to_period(cls, data: Any) -> Any:
        """Accepts scenario files from before the switch to period (wavelength `length` in m)."""
        if isinstance(data, dict) and "length" in data and "period" not in data:
            length = float(data["length"])
            data = {k: v for k, v in data.items() if k != "length"}
            data["period"] = round(math.sqrt(2 * math.pi * max(length, 1.0) / G), 1)
        return data


class Seabed(BaseModel):
    fixed: bool = False
    depth: float = 20.0  # m, used when fixed
    depth_min: float = 12.0
    depth_max: float = 35.0
    change_period_min: float = 5.0
    transducer_depth: float = 0.5  # m below waterline
    keel_depth: float = 1.8  # m below waterline (transducer offset = transducer − keel)


class Boat(BaseModel):
    lat: float = 43.48
    lon: float = 16.40
    polar_file: str = "mock_cruiser_40.pol"
    leeway_k: float = 10.0  # boat constant for λ = K·heel/STW²
    stw_time_constant_s: float = 8.0
    max_turn_rate: float = 6.0  # deg/s
    motor_speed_per_1000rpm: float = 2.6  # kn per 1000 rpm


class Autopilot(BaseModel):
    mode: Literal["heading", "twa", "motor"] = "twa"
    heading: float = 0.0  # deg true, target for heading / motor modes
    twa: float = -45.0  # deg, signed (negative = port tack: wind from port)
    rpm: float = 2200.0  # motor mode


class Gps(BaseModel):
    variation: float = 4.5  # deg, east positive
    altitude: float = 2.0
    geoidal_separation: float = 45.0
    local_offset_min: float = 120.0
    hdop: float = 0.8
    vdop: float = 1.2
    pdop: float = 1.4
    tdop: float = 0.9
    sats_used: int = 12
    sats_in_view: int = 14


class Processor(BaseModel):
    leeway_k: float = 10.0  # K used by the instrument processor for leeway correction


DEFAULT_STATIC: dict[str, float] = {
    "water_temp": 19.0,
    "air_temp": 22.0,
    "pressure": 1013.2,
    "humidity": 65.0,
    "cabin_temp": 24.0,
    "engine.rpm": 0.0,
    "engine.oil_pressure": 3.5,
    "engine.oil_temp": 90.0,
    "engine.coolant_temp": 80.0,
    "engine.alternator_v": 14.2,
    "engine.fuel_rate": 2.5,
    "engine.hours": 1250.0,
    "engine.load": 40.0,
    "tank.fuel.level": 75.0,
    "tank.fuel.capacity": 200.0,
    "tank.fresh_water1.level": 60.0,
    "tank.fresh_water1.capacity": 300.0,
    "tank.fresh_water2.level": 90.0,
    "tank.fresh_water2.capacity": 150.0,
    "tank.black_water.level": 20.0,
    "tank.black_water.capacity": 80.0,
    "battery.house.voltage": 12.6,
    "battery.house.current": -4.2,
    "battery.house.temp": 25.0,
    "battery.engine.voltage": 12.8,
    "battery.engine.current": 0.0,
    "battery.engine.temp": 22.0,
}


class Transport(BaseModel):
    enabled: bool = True
    host: str
    port: int


class PgnSetting(BaseModel):
    enabled: bool = True
    interval_s: float | None = None  # None = default from the PGN table


class Output(BaseModel):
    source: int = 0x23
    udp: Transport = Field(default_factory=lambda: Transport(host="255.255.255.255", port=2002))
    tcp: Transport = Field(default_factory=lambda: Transport(host="0.0.0.0", port=2223))
    recorder: bool = False
    pgns: dict[str, PgnSetting] = Field(default_factory=dict)


class Scenario(BaseModel):
    seed: int = 1
    wind: Wind = Field(default_factory=Wind)
    current: Current = Field(default_factory=Current)
    waves: Waves = Field(default_factory=Waves)
    seabed: Seabed = Field(default_factory=Seabed)
    boat: Boat = Field(default_factory=Boat)
    autopilot: Autopilot = Field(default_factory=Autopilot)
    gps: Gps = Field(default_factory=Gps)
    processor: Processor = Field(default_factory=Processor)
    static: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_STATIC))
    overrides: dict[str, float] = Field(default_factory=dict)  # signal name -> UI-unit value
    output: Output = Field(default_factory=Output)

    @classmethod
    def load(cls, path: Path) -> "Scenario":
        return cls.model_validate(json.loads(Path(path).read_text()))

    def save(self, path: Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))


SECTIONS = ("wind", "current", "waves", "seabed", "boat", "autopilot", "gps", "processor")
