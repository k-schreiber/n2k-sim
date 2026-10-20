"""Shared fixtures: a full signal snapshot and an encode-to-YD-RAW helper."""

from __future__ import annotations

import math

import pytest

from n2k_sim.formats.ydraw import format_frame
from n2k_sim.n2k.canid import build_can_id
from n2k_sim.n2k.fastpacket import FastPacketFramer
from n2k_sim.n2k.types import CanFrame

D = math.radians

SIGNALS = {
    "awa": D(-35.0), "aws": 7.2, "twa": D(-120.0), "tws": 6.1, "twd": D(250.0),
    "gws": 6.4, "gwa": D(-110.0), "gwd": D(260.0),
    "heading_mag": D(123.4), "rot": D(1.5) / 60, "yaw": D(123.4), "pitch": D(-2.0), "roll": D(15.0),
    "rudder": D(-5.5), "stw": 3.4, "log_total": 1234567.0, "log_trip": 5432.0,
    "water_temp": 288.15, "depth": 12.34, "depth_offset": -1.8,
    "lat": 54.123456, "lon": -10.654321, "cog": D(95.0), "sog": 3.6,
    "gnss_time": 1_700_000_000.1234, "local_offset": 120.0, "variation": D(4.5),
    "altitude": 12.5, "geoidal_separation": 44.3, "gnss_type": 0, "fix_method": 1, "fix_mode": 2,
    "sats_used": 9, "sats_in_view": 2, "hdop": 0.9, "vdop": 1.2, "pdop": 1.5, "tdop": 1.1,
    "satellites": [(5, D(45), D(120), 41.5, 2), (17, D(10), D(300), 30.0, 1)],
    "dew_point": 288.0, "current_set": D(200.0), "current_drift": 0.5,
    "air_temp": 295.15, "pressure": 101320.0, "humidity": 65.0, "cabin_temp": 297.15,
    "engine.rpm": 2400.0, "engine.oil_pressure": 350000.0, "engine.oil_temp": 363.15,
    "engine.coolant_temp": 353.15, "engine.alternator_v": 14.2, "engine.fuel_rate": 2.5,
    "engine.hours": 1250 * 3600.0, "engine.load": 40.0,
    "tank.fuel.level": 75.0, "tank.fuel.capacity": 200.0,
    "tank.fresh_water1.level": 60.0, "tank.fresh_water1.capacity": 300.0,
    "tank.fresh_water2.level": 90.0, "tank.fresh_water2.capacity": 150.0,
    "tank.black_water.level": 20.0, "tank.black_water.capacity": 80.0,
    "battery.house.voltage": 12.6, "battery.house.current": -4.2, "battery.house.temp": 298.15,
    "battery.engine.voltage": 12.8, "battery.engine.current": 0.0, "battery.engine.temp": 295.15,
}


@pytest.fixture
def signals() -> dict:
    return dict(SIGNALS)


@pytest.fixture
def run():
    """Returns run(spec, signals) -> YD RAW lines for all payloads of one emission."""
    framer = FastPacketFramer()

    def _run(spec, sig, sid=7):
        lines = []
        for payload in spec.encode(sig, sid):
            can_id = build_can_id(spec.priority, spec.pgn, 0x23)
            for data in framer.frames(spec.pgn, payload, spec.fast_packet):
                lines.append(format_frame(CanFrame(can_id, data, 1_700_000_000.5)))
        return lines

    return _run
