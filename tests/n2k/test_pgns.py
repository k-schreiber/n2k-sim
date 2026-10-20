"""Decode round trips for every encoder plus golden bytes per PGN family."""

from __future__ import annotations

import math

import pytest

from n2k_sim.n2k.pgns import default_pgns
from n2k_sim.n2k.pgns import system
from n2k_sim.signals.catalogue import BATTERIES, TANKS

from . import decoder as dec

SPECS = {s.id: s for s in default_pgns()}
D = math.radians


def decode_all(run, key, sig, sid=7):
    """Encodes one emission and returns [(pgn, payload, decoded)]."""
    lines = run(SPECS[key], sig, sid)
    return [(p, b, dec.decode_payload(p, b)) for p, b in dec.reassemble(lines)]


def one(run, key, sig, sid=7):
    out = decode_all(run, key, sig, sid)
    assert len(out) == 1
    return out[0][1], out[0][2]


def close(a, b, res):
    assert a is not None and abs(a - b) <= res / 2 + 1e-9, (a, b, res)


def wrap(a):
    return a % (2 * math.pi)


def test_schedule():
    ids = set(SPECS)
    assert {"130306.apparent", "130306.true", "130306.ground"} <= ids
    assert "60928" not in ids and len(default_pgns()) == len(ids)
    assert {s.pgn for s in SPECS.values() if s.fast_packet} == {127489, 128275, 129029, 129540}
    assert not SPECS["130310"].enabled and SPECS["130311"].enabled
    assert SPECS["130306.apparent"].interval_s == 0.1 and SPECS["127258"].priority == 7
    assert {s.sensor for s in SPECS.values()} <= {
        "gps", "compass", "wind_sensor", "speed_log", "depth_sounder", "rudder", "engine",
        "tanks", "battery", "weather", "processor", "gateway"}


def test_every_single_frame_payload_is_8_bytes(run, signals):
    for spec in default_pgns():
        for payload in spec.encode(signals, 1):
            if not spec.fast_packet:
                assert len(payload) == 8, spec.id


def test_fast_packet_lengths(run, signals):
    for key, n in (("127489", 26), ("128275", 14), ("129029", 43), ("129540", 3 + 24)):
        (payload,) = SPECS[key].encode(signals, 1)
        assert len(payload) == n


def test_none_everywhere_gives_sentinels(signals):
    empty = {}
    for spec in default_pgns():
        for payload in spec.encode(empty, 3):
            assert len(payload) >= 3  # never raises
    assert SPECS["129025"].encode(empty, 0)[0] == b"\xff\xff\xff\x7f\xff\xff\xff\x7f"


# ---- system -------------------------------------------------------------------------------


def test_126992(run, signals):
    _, d = one(run, "126992", signals)
    assert d["sid"] == 7 and d["source"] == 0xF0
    assert d["date"] == 19675
    close(d["time"], 80000.1234, 1e-4)


def test_129033(run, signals):
    _, d = one(run, "129033", signals)
    assert d["date"] == 19675 and d["offset"] == 120
    close(d["time"], 80000.1234, 1e-4)


def test_address_claim_golden():
    name = dict(unique_number=0x12345, manufacturer_code=2046, device_instance=0, device_function=136,
                device_class=25, system_instance=0, industry_group=4, arbitrary_address=True)
    got = system.address_claim(name)
    low = int.from_bytes(got[:4], "little")
    assert low & 0x1FFFFF == 0x12345 and low >> 21 == 2046
    assert got[4:] == bytes([0, 136, 25 << 1 | 1, 0xC0])


# ---- gps ----------------------------------------------------------------------------------


def test_129025(run, signals):
    _, d = one(run, "129025", signals)
    close(d["lat"], 54.123456, 1e-7)
    close(d["lon"], -10.654321, 1e-7)


def test_129025_golden(signals):
    assert SPECS["129025"].encode({"lat": 1.0, "lon": -1.0}, 0)[0] == bytes.fromhex("80969800" "806967ff")


def test_129026(run, signals):
    _, d = one(run, "129026", signals)
    assert d["ref"] & 3 == 0
    close(d["cog"], D(95), 1e-4)
    close(d["sog"], 3.6, 0.01)


def test_129029(run, signals):
    payload, d = one(run, "129029", signals)
    assert len(payload) == 43 and d["refstations"] == 0
    close(d["lat"], 54.123456, 1e-9)
    close(d["lon"], -10.654321, 1e-9)
    close(d["altitude"], 12.5, 1e-6)
    assert d["type_method"] == 0x10 and d["integrity"] & 3 == 0 and d["sats"] == 9
    close(d["hdop"], 0.9, 0.01)
    close(d["pdop"], 1.5, 0.01)
    close(d["geoid"], 44.3, 0.01)
    assert d["date"] == 19675


def test_129539(run, signals):
    _, d = one(run, "129539", signals)
    assert d["mode"] & 7 == 2 and (d["mode"] >> 3) & 7 == 2
    close(d["hdop"], 0.9, 0.01)
    close(d["vdop"], 1.2, 0.01)
    close(d["tdop"], 1.1, 0.01)


def test_129540(run, signals):
    payload, d = one(run, "129540", signals)
    assert d["length"] == 27 and d["n"] == 2
    s0, s1 = d["sats"]
    assert s0["prn"] == 5 and s0["status"] == 2 and s0["residual"] is None
    close(s0["elevation"], D(45), 1e-4)
    close(s0["azimuth"], D(120), 1e-4)
    close(s0["snr"], 41.5, 0.01)
    assert s1["prn"] == 17 and s1["status"] == 1
    close(s1["azimuth"], D(300), 1e-4)


def test_129540_none_and_empty(run, signals):
    assert SPECS["129540"].encode({**signals, "satellites": None}, 0) == []
    (p,) = SPECS["129540"].encode({**signals, "satellites": []}, 0)
    assert len(p) == 3 and p[2] == 0


def test_129540_many_sats_truncated(signals):
    sats = [(i, 0.5, 1.0, 40.0, 2) for i in range(30)]
    (p,) = SPECS["129540"].encode({**signals, "satellites": sats}, 0)
    assert len(p) == 3 + 12 * 18 <= 223


def test_127258(run, signals):
    _, d = one(run, "127258", signals)
    assert d["source"] & 0x0F == 8 and d["age"] is None
    close(d["variation"], D(4.5), 1e-4)


# ---- compass ------------------------------------------------------------------------------


def test_127250(run, signals):
    _, d = one(run, "127250", signals)
    close(d["heading"], D(123.4), 1e-4)
    assert d["reference"] == 1 and d["deviation"] is None
    close(d["variation"], D(4.5), 1e-4)


def test_127250_golden(signals):
    got = SPECS["127250"].encode({"heading_mag": 1.0}, 9)[0]
    assert got == bytes([9, 0x10, 0x27, 0xFF, 0x7F, 0xFF, 0x7F, 0xFD])
    # 4.5° E = 0.07854 rad -> 785 = 0x0311, east positive.
    got = SPECS["127250"].encode({"heading_mag": 1.0, "variation": 0.0785398}, 9)[0]
    assert got == bytes([9, 0x10, 0x27, 0xFF, 0x7F, 0x11, 0x03, 0xFD])


def test_127251(run, signals):
    _, d = one(run, "127251", signals)
    close(d["rate"], D(1.5) / 60, 3.125e-8)


def test_127251_negative(run, signals):
    _, d = one(run, "127251", {"rot": -0.01})
    close(d["rate"], -0.01, 3.125e-8)


def test_127257(run, signals):
    _, d = one(run, "127257", signals)
    close(d["yaw"], D(123.4), 1e-4)
    close(d["pitch"], D(-2), 1e-4)
    close(d["roll"], D(15), 1e-4)


# ---- wind ---------------------------------------------------------------------------------


def test_wind_apparent(run, signals):
    _, d = one(run, "130306.apparent", signals)
    assert d["reference"] == 2
    close(d["angle"], wrap(D(-35)), 1e-4)
    close(d["speed"], 7.2, 0.01)


def test_wind_true_boat(run, signals):
    _, d = one(run, "130306.true", signals)
    assert d["reference"] == 3
    close(d["angle"], wrap(D(-120)), 1e-4)
    close(d["speed"], 6.1, 0.01)


def test_wind_ground(run, signals):
    _, d = one(run, "130306.ground", signals)
    assert d["reference"] == 0
    close(d["angle"], D(250), 1e-4)
    close(d["speed"], 6.1, 0.01)


def test_wind_golden():
    got = SPECS["130306.apparent"].encode({"awa": -math.pi / 2, "aws": 10.0}, 1)[0]
    assert got == bytes([1]) + (1000).to_bytes(2, "little") + (47124).to_bytes(2, "little") + b"\xfa\xff\xff"


# ---- log / depth --------------------------------------------------------------------------


def test_128259(run, signals):
    _, d = one(run, "128259", signals)
    close(d["stw"], 3.4, 0.01)
    assert d["sog"] is None


def test_128259_golden():
    assert SPECS["128259"].encode({"stw": 3.4}, 2)[0] == bytes([2, 0x54, 0x01, 0xFF, 0xFF, 0, 0xFF, 0xFF])


def test_128275(run, signals):
    payload, d = one(run, "128275", signals)
    assert len(payload) == 14 and d["log"] == 1234567 and d["trip"] == 5432 and d["date"] == 19675


def test_128267(run, signals):
    _, d = one(run, "128267", signals)
    close(d["depth"], 12.34, 0.01)
    close(d["offset"], -1.8, 0.001)
    assert d["range"] is None


def test_128267_golden():
    got = SPECS["128267"].encode({"depth": 5.0, "depth_offset": -1.8}, 4)[0]
    assert got == bytes([4]) + (500).to_bytes(4, "little") + (-1800).to_bytes(2, "little", signed=True) + b"\xff"


# ---- steering / processor -----------------------------------------------------------------


def test_127245(run, signals):
    _, d = one(run, "127245", signals)
    close(d["position"], D(-5.5), 1e-4)
    assert d["order"] is None


def test_129291(run, signals):
    _, d = one(run, "129291", signals)
    close(d["set"], D(200), 1e-4)
    close(d["drift"], 0.5, 0.01)
    assert d["ref"] & 3 == 0


# ---- engine -------------------------------------------------------------------------------


def test_127488(run, signals):
    _, d = one(run, "127488", signals)
    close(d["rpm"], 2400.0, 0.25)
    assert d["boost"] is None and d["trim"] is None


def test_127488_golden():
    got = SPECS["127488"].encode({"engine.rpm": 2400.0}, 0)[0]
    assert got == bytes([0]) + (9600).to_bytes(2, "little") + b"\xff\xff\x7f\xff\xff"


def test_127489(run, signals):
    payload, d = one(run, "127489", signals)
    assert len(payload) == 26
    close(d["oil_pressure"], 350000, 100)
    close(d["oil_temp"], 363.15, 0.1)
    close(d["coolant_temp"], 353.15, 0.01)
    close(d["alternator"], 14.2, 0.01)
    close(d["fuel_rate"], 2.5, 0.1)
    assert d["hours"] == 1250 * 3600
    assert d["coolant_pressure"] is None and d["fuel_pressure"] is None
    assert d["load"] == 40 and d["torque"] is None


@pytest.mark.parametrize("rpm", [None, 0, 0.0])
def test_engine_off_sends_nothing(signals, rpm):
    sig = {**signals, "engine.rpm": rpm}
    assert SPECS["127488"].encode(sig, 0) == [] and SPECS["127489"].encode(sig, 0) == []


# ---- tanks / batteries --------------------------------------------------------------------


def test_127505(run, signals):
    out = decode_all(run, "127505", signals)
    assert len(out) == len(TANKS)
    for (_, payload, d), (prefix, instance, fluid) in zip(out, TANKS):
        assert d["instance"] == instance and d["fluid"] == fluid
        close(d["level"], signals[prefix + ".level"], 0.004)
        close(d["capacity"], signals[prefix + ".capacity"], 0.1)
        assert payload[7] == 0xFF


def test_127505_golden():
    sig = {"tank.fuel.level": 75.0, "tank.fuel.capacity": 200.0}
    got = SPECS["127505"].encode(sig, 0)[0]
    assert got == bytes([0x00]) + (18750).to_bytes(2, "little") + (2000).to_bytes(4, "little") + b"\xff"


def test_127508(run, signals):
    out = decode_all(run, "127508", signals, sid=9)
    assert len(out) == len(BATTERIES)
    for (_, _, d), (prefix, instance) in zip(out, BATTERIES):
        assert d["instance"] == instance and d["sid"] == 9
        close(d["voltage"], signals[prefix + ".voltage"], 0.01)
        close(d["current"], signals[prefix + ".current"], 0.1)
        close(d["temp"], signals[prefix + ".temp"], 0.01)


def test_127508_golden():
    sig = {"battery.house.voltage": 12.6, "battery.house.current": -4.2, "battery.house.temp": 298.15}
    got = SPECS["127508"].encode(sig, 5)[0]
    assert got == bytes([0]) + (1260).to_bytes(2, "little") + (-42).to_bytes(2, "little", signed=True) \
        + (29815).to_bytes(2, "little") + bytes([5])


# ---- environment --------------------------------------------------------------------------


def test_130310(run, signals):
    _, d = one(run, "130310", signals)
    close(d["water_temp"], 288.15, 0.01)
    close(d["air_temp"], 295.15, 0.01)
    close(d["pressure"], 101320.0, 100.0)


def test_130311(run, signals):
    _, d = one(run, "130311", signals)
    assert d["temp_source"] == 1 and d["humidity_source"] == 1
    close(d["temp"], 295.15, 0.01)
    close(d["humidity"], 65.0, 0.004)
    close(d["pressure"], 101320.0, 100.0)


def test_130311_golden(signals):
    got = SPECS["130311"].encode({"air_temp": 295.15, "humidity": 65.0, "pressure": 101300.0}, 3)[0]
    assert got == bytes([3, 0x41]) + (29515).to_bytes(2, "little") + (16250).to_bytes(2, "little") \
        + (1013).to_bytes(2, "little")


def test_130312_two_payloads(run, signals):
    out = decode_all(run, "130312", signals)
    assert len(out) == 2
    (_, _, water), (_, _, cabin) = out
    assert (water["instance"], water["source"]) == (0, 0)
    assert (cabin["instance"], cabin["source"]) == (1, 4)
    close(water["temp"], 288.15, 0.01)
    close(cabin["temp"], 297.15, 0.01)
    assert water["set"] is None


def test_130313(run, signals):
    _, d = one(run, "130313", signals)
    assert d["source"] == 1 and d["set"] is None
    close(d["humidity"], 65.0, 0.004)


def test_130314(run, signals):
    _, d = one(run, "130314", signals)
    assert d["source"] == 0
    close(d["pressure"], 101320.0, 0.1)


def test_130316(run, signals):
    _, d = one(run, "130316", signals)
    assert d["source"] == 9 and d["set"] is None
    close(d["temp"], 288.0, 0.001)


def test_130316_golden():
    got = SPECS["130316"].encode({"dew_point": 288.0}, 1)[0]
    assert got == bytes([1, 0, 9]) + (288000).to_bytes(3, "little") + b"\xff\xff"
