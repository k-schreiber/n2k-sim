"""Every PGN against canboat, the golden source for NMEA 2000: framing, length, priority, reserved
bits and transmission interval. Skipped when the canboat repository isn't next to n2k-sim."""

import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

from n2k_sim.config import Device, Scenario
from n2k_sim.n2k.device import BusDevice
from n2k_sim.n2k.pgns import default_pgns
from n2k_sim.simulation import Simulation

CANBOAT = Path(__file__).resolve().parents[3] / "canboat" / "docs" / "canboat.json"
# Deliberately faster than canboat's nominal rate: the analysis needs attitude at 10 Hz.
FASTER_ON_PURPOSE = {"127257"}

pytestmark = pytest.mark.skipif(not CANBOAT.is_file(), reason="canboat repository not available")


@pytest.fixture(scope="module")
def definitions():
    by_pgn = defaultdict(list)
    for definition in json.loads(CANBOAT.read_text())["PGNs"]:
        by_pgn[definition["PGN"]].append(definition)
    return by_pgn


@pytest.fixture(scope="module")
def signals():
    s = Scenario()
    s.static["engine.rpm"] = 2000.0
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    snapshot = None
    for _ in range(100):
        snapshot = sim.step(0.1)
    return snapshot.sent


def bits(payload: bytes, offset: int, length: int) -> int:
    return (int.from_bytes(payload, "little") >> offset) & ((1 << length) - 1)


def pick(definitions, pgn: int, payload: bytes) -> dict:
    """The definition whose `Match` fields fit the payload."""
    for d in definitions[pgn]:
        offset, fits = 0, True
        for field in d["Fields"]:
            length = field.get("BitLength")
            if length is None:
                break
            if "Match" in field and bits(payload, offset, length) != field["Match"]:
                fits = False
            offset += length
        if fits:
            return d
    pytest.fail(f"no canboat definition of {pgn} fits")


def check(definition: dict, payload: bytes, fast: bool, priority: int) -> None:
    assert (definition["Type"] == "Fast") == fast
    assert definition.get("Priority", priority) == priority
    if definition.get("Length") and not definition.get("MinLength"):
        assert len(payload) == definition["Length"]
    assert len(payload) >= (definition.get("MinLength") or 0)
    offset = 0
    for field in definition["Fields"]:
        length = field.get("BitLength")
        if length is None or field["Order"] >= definition.get("RepeatingFieldSet1StartField", math.inf):
            break
        if field["FieldType"] == "RESERVED":
            assert bits(payload, offset, length) == (1 << length) - 1, field["Id"]
        offset += length
    if not definition.get("RepeatingFieldSet1Size"):
        assert offset <= len(payload) * 8


@pytest.mark.parametrize("spec", default_pgns(), ids=lambda s: s.id)
def test_schedule_matches_canboat(spec, definitions, signals):
    payloads = spec.encode(signals, 7)
    assert payloads
    for payload in payloads:
        definition = pick(definitions, spec.pgn, payload)
        check(definition, payload, spec.fast_packet, spec.priority)
        interval = definition.get("TransmissionInterval")
        if interval and spec.id not in FASTER_ON_PURPOSE and spec.pgn != 130306:  # 130306: per reference
            assert spec.interval_s == pytest.approx(interval / 1000)


def test_identity_matches_canboat(definitions):
    device = BusDevice(Device(installation_description2="Mast"), 0x23)
    for m in device.identity() + device.pgn_lists({130306}, 5):
        check(pick(definitions, m.pgn, m.payload), m.payload, m.fast, m.priority)
