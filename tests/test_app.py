"""API and end-to-end tests: run the real app, read the TCP and UDP streams and decode them."""

import math
import socket
import time

import pytest
from fastapi.testclient import TestClient

from n2k_sim.app import Runtime
from n2k_sim.config import Scenario
from n2k_sim.units import ms_to_kn
from n2k_sim.web.api import create_app

from .n2k.decoder import decode_payload, reassemble


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ports():
    return free_port(), free_port(socket.SOCK_DGRAM)


@pytest.fixture
def client(ports):
    tcp_port, udp_port = ports
    scenario = Scenario()
    scenario.output.tcp.host = "127.0.0.1"
    scenario.output.tcp.port = tcp_port
    scenario.output.udp.host = "127.0.0.1"
    scenario.output.udp.port = udp_port
    runtime = Runtime(scenario)
    with TestClient(create_app(runtime)) as c:
        c.runtime = runtime
        yield c


def read_tcp(port: int, seconds: float) -> list[str]:
    data = b""
    with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
        s.settimeout(0.2)
        end = time.time() + seconds
        while time.time() < end:
            try:
                data += s.recv(65536)
            except socket.timeout:
                pass
    text = data.decode("ascii")
    return [line for line in text.split("\r\n")[:-1] if line]


def wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met")


def test_index_and_state(client):
    assert client.get("/").status_code == 200
    state = client.get("/api/state").json()
    names = {s["name"] for s in state["signals"]}
    assert {"aws", "twd", "engine.rpm", "env.gwd"} <= names
    assert state["output"]["tcp"]["port"] == client.runtime.scenario.output.tcp.port
    assert len(state["output"]["pgns"]) >= 25


def test_tcp_stream_decodes_to_snapshot(client, ports):
    lines = read_tcp(ports[0], 2.5)
    assert len(lines) > 100
    for line in lines:
        tok = line.split(" ")
        assert tok[1] == "R" and len(tok[2]) == 8 and 1 <= len(tok) - 3 <= 8
    payloads = reassemble(lines)
    pgns = {pgn for pgn, _ in payloads}
    # 60928 is claimed at start-up (before this client connected) and every 5 minutes.
    assert {127250, 128259, 129025, 129026, 129029, 130306, 127505} <= pgns
    snap = client.runtime.sim.snapshot.sent
    winds = [decode_payload(p, d) for p, d in payloads if p == 130306]
    apparent = [w for w in winds if w["reference"] == 2][-1]
    assert apparent["speed"] == pytest.approx(snap["aws"], abs=0.5)
    pos = [decode_payload(p, d) for p, d in payloads if p == 129025][-1]
    assert pos["lat"] == pytest.approx(snap["lat"], abs=1e-3)


def test_udp_broadcast_datagrams(client, ports):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", ports[1]))
    sock.settimeout(2)
    try:
        datagram, _ = sock.recvfrom(65536)
    finally:
        sock.close()
    assert len(datagram) <= 1400
    assert datagram.endswith(b"\r\n") and b" R " in datagram


def test_override_is_transmitted_but_not_used_in_calculation(client):
    assert client.put("/api/overrides/aws", json={"value": 30}).json() == {"ok": True}
    wait_for(lambda: abs(ms_to_kn(client.runtime.sim.snapshot.sent["aws"]) - 30) < 0.01)
    snap = client.runtime.sim.snapshot
    assert ms_to_kn(snap.values["aws"]) < 25
    row = next(s for s in client.get("/api/state").json()["signals"] if s["name"] == "aws")
    assert row["overridden"] and row["sent"] == pytest.approx(30)
    assert client.delete("/api/overrides/aws").status_code == 200
    assert client.put("/api/overrides/env.gws", json={"value": 3}).status_code == 400


def test_patch_sections_and_static(client):
    assert client.patch("/api/scenario/wind", json={"fixed": True, "tws": 20}).status_code == 200
    assert client.runtime.scenario.wind.tws == 20
    assert client.patch("/api/scenario/nope", json={}).status_code == 400
    assert client.patch("/api/static", json={"engine.rpm": 1500}).status_code == 200
    wait_for(lambda: client.runtime.sim.snapshot.values["engine.rpm"] == 1500)
    assert client.patch("/api/static", json={"aws": 3}).status_code == 400


def test_autopilot_tack_and_adjust(client):
    client.patch("/api/scenario/autopilot", json={"mode": "twa", "twa": -45})
    client.post("/api/autopilot/tack")
    assert client.runtime.scenario.autopilot.twa == 45
    client.post("/api/autopilot/adjust", json={"delta": 10})
    assert client.runtime.scenario.autopilot.twa == 35


def test_pgn_disable_and_interval(client, ports):
    assert client.patch("/api/output/pgns/129540", json={"enabled": False}).status_code == 200
    assert client.patch("/api/output/pgns/130306.apparent", json={"interval_s": 0.5}).status_code == 200
    lines = read_tcp(ports[0], 2.2)
    payloads = reassemble(lines)
    assert all(p != 129540 for p, _ in payloads)
    apparent = [d for p, d in payloads if p == 130306 and decode_payload(p, d)["reference"] == 2]
    assert 3 <= len(apparent) <= 6


def test_polar_roundtrip_and_validation(client):
    polar = client.get("/api/polar").json()
    assert polar["tws"][0] == 4 and len(polar["speed"]) == len(polar["twa"])
    assert client.put("/api/polar", content="garbage").status_code == 400


def test_scenario_put_resets(client):
    scenario = client.get("/api/scenario").json()
    scenario["autopilot"]["mode"] = "motor"
    assert client.put("/api/scenario", json=scenario).status_code == 200
    assert client.runtime.scenario.autopilot.mode == "motor"


def test_websocket_pushes_state_and_raw(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state" and "signals" in msg
        ws.send_json({"subscribe": "raw"})
        for _ in range(10):
            msg = ws.receive_json()
            if msg["type"] == "raw":
                assert msg["lines"] and " R " in msg["lines"][0]
                break
        else:
            pytest.fail("no raw lines pushed")


def test_websocket_motion_stream(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"subscribe": "motion"})
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] == "motion":
                assert msg["valid"] and {"roll", "pitch", "heel", "awa", "wave"} <= set(msg)
                assert {"height", "length", "mu", "phase"} <= set(msg["wave"])
                break
        else:
            pytest.fail("no motion message")
