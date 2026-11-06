"""The simulator as a bus device: what Signal K's device management sends and expects. The input
frames are real canboatjs output (docs/spec/n2k-output.md)."""

import asyncio

import pytest

from n2k_sim.app import Runtime
from n2k_sim.config import Device, Scenario
from n2k_sim.formats.ydraw import parse_client_line
from n2k_sim.n2k.canid import build_can_id, parse_can_id
from n2k_sim.n2k.device import host_unique_number
from n2k_sim.n2k.fastpacket import FastPacketAssembler
from n2k_sim.n2k.gateway import IDENTITY_INTERVAL, Gateway
from n2k_sim.n2k.pgns import system

SOURCE = 0x23
ME = 0x64  # the requesting device
NOW = 1_760_000_000.0


def gateway(**device) -> Gateway:
    return Gateway(SOURCE, device=Device(**device))


def request(gw: Gateway, pgn: int, destination: int = SOURCE, source: int = ME):
    can_id = build_can_id(6, 59904, source, destination)
    return gw.receive(can_id, pgn.to_bytes(3, "little"), NOW)


def client_frames(gw: Gateway, lines: list[str]):
    out = []
    for line in lines:
        out += gw.receive(*parse_client_line(line), NOW)
    return out


def messages(frames) -> dict[int, bytes]:
    """Reassembles frames into {pgn: last payload}."""
    assembler, out = FastPacketAssembler(), {}
    fast = {126208, 126464, 126996, 126998}
    for f in frames:
        pgn = parse_can_id(f.can_id)[1]
        data = assembler.add(0, pgn, f.data) if pgn in fast else f.data
        if data is not None:
            out[pgn] = data
    return out


def test_name_fields_follow_canboat():
    name = gateway(unique_number=0x12345, device_instance=0b10101011, system_instance=5).device.name()
    n = int.from_bytes(name, "little")
    assert n & 0x1FFFFF == 0x12345
    assert (n >> 21) & 0x7FF == 2046
    assert (n >> 32) & 7 == 0b011 and (n >> 35) & 0x1F == 0b10101  # device instance lower, upper
    assert (n >> 40) & 0xFF == 136  # NMEA Network Gateway
    assert (n >> 48) & 1 == 0 and (n >> 49) & 0x7F == 25  # spare, Internetwork device
    assert (n >> 56) & 0xF == 5 and (n >> 60) & 7 == 4 and n >> 63 == 1  # system, marine, arbitrary


def test_unique_number_is_stable_and_never_the_unset_value():
    assert gateway().device.unique_number == host_unique_number() != 0x1FFFFF


def test_product_information_layout():
    payload = messages(gateway(unique_number=4711).announce(NOW))[126996]
    assert len(payload) == 134
    assert int.from_bytes(payload[:2], "little") == 2101
    assert int.from_bytes(payload[2:4], "little") == 2000
    assert payload[4:36].rstrip(b"\xff") == b"n2k-sim"
    assert payload[100:132].rstrip(b"\xff") == b"4711"  # serial, same as the unique number
    assert payload[132:] == bytes([1, 1])


def test_configuration_information_is_labelled_simulated():
    payload = messages(gateway(installation_description2="Mast").announce(NOW))[126998]
    assert payload[:11] == b"\x0b\x01Simulator"
    assert payload[11:17] == b"\x06\x01Mast"
    assert payload[19:].startswith(b"Simulated data") and payload[17:19] == bytes([36, 1])


def test_identity_comes_first_and_repeats_for_receive_only_links():
    gw = gateway()
    first = gw.poll(NOW, {})
    assert parse_can_id(first[0].can_id)[1] == 60928
    assert parse_can_id(gw.poll(NOW + 1, {})[0].can_id)[1] != 60928
    pgns = {parse_can_id(f.can_id)[1] for f in gw.poll(NOW + IDENTITY_INTERVAL, {})}
    assert {60928, 126996, 126998} <= pgns


def test_heartbeat_is_scheduled_and_encoded():
    gw = gateway()
    spec = gw.specs["126993"]
    assert (spec.interval_s, spec.priority) == (60.0, 7)
    assert spec.encode({}, 9)[0] == bytes([0x60, 0xEA, 9, 0xC0]) + b"\xff" * 4


@pytest.mark.parametrize("pgn", [60928, 126996, 126998])
@pytest.mark.parametrize("destination", [SOURCE, 0xFF])
def test_discovery_requests_are_answered(pgn, destination):
    """Signal K's sweep: 60928, 126996 and 126998 from each address, one at a time."""
    frames = request(gateway(), pgn, destination)
    assert {parse_can_id(f.can_id)[1] for f in frames} == {pgn}
    assert all(parse_can_id(f.can_id)[2] == SOURCE for f in frames)


def test_request_of_a_real_canboatjs_frame():
    frames = client_frames(gateway(), ["18ea2300 14 f0 01"])
    assert 126996 in messages(frames)


def test_request_from_a_device_without_address_is_answered_globally():
    frames = request(gateway(), 126464, 0xFF, source=254)
    assert {parse_can_id(f.can_id)[3] for f in frames} == {0xFF}


def test_pgn_lists_go_to_the_requester():
    frames = request(gateway(), 126464)
    assert {parse_can_id(f.can_id)[3] for f in frames} == {ME}
    assembler, lists = FastPacketAssembler(), {}
    for f in frames:
        data = assembler.add(0, 126464, f.data)
        if data is not None:
            lists[data[0]] = {int.from_bytes(data[i:i + 3], "little") for i in range(1, len(data), 3)}
    assert {60928, 126996, 126998, 126993, 130306, 129029} <= lists[0]
    assert lists[1] == {59904, 60928, 126208}


def test_a_scheduled_pgn_is_sent_on_request():
    gw = gateway()
    gw.poll(NOW, {"gnss_time": NOW})
    assert 126992 in messages(request(gw, 126992))


def test_unknown_pgn_gets_a_nak_only_when_addressed():
    frames = request(gateway(), 65000)
    assert len(frames) == 1
    _, pgn, _, destination = parse_can_id(frames[0].can_id)
    assert (pgn, destination) == (59392, ME)
    assert frames[0].data == bytes([1, 0xFF, 0xFF, 0xFF, 0xFF]) + (65000).to_bytes(3, "little")
    assert request(gateway(), 65000, 0xFF) == []


def test_frames_for_another_device_are_ignored():
    assert request(gateway(), 126996, 0x30) == []


def test_lower_name_keeps_the_address_and_reclaims():
    gw = gateway(unique_number=100)
    higher = (0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
    frames = gw.receive(build_can_id(6, 60928, SOURCE), higher, NOW)
    assert gw.source == SOURCE and frames[0].data == gw.device.name()


def test_higher_name_moves_to_a_free_address_and_claims_it():
    gw = gateway(unique_number=100)
    gw.receive(build_can_id(6, 60928, SOURCE + 1), bytes(7) + b"\x01", NOW)  # next address is taken
    frames = gw.receive(build_can_id(6, 60928, SOURCE), bytes(8), NOW)
    assert gw.source == SOURCE + 2
    assert parse_can_id(frames[0].can_id)[2] == SOURCE + 2 and frames[0].data == gw.device.name()


def test_own_name_on_own_address_is_no_conflict():
    gw = gateway()
    assert gw.receive(build_can_id(6, 60928, SOURCE), gw.device.name(), NOW) == []


def test_command_sets_data_instance_from_a_plain_8_byte_frame():
    """canboatjs sends a fast-packet message of exactly 8 bytes without the fast-packet header."""
    gw = gateway()
    frames = client_frames(gw, ["0ded2300 01 00 ee 00 f8 01 03 05"])
    assert gw.device.cfg.device_instance == 5
    assert messages(frames)[126208] == bytes([2, 0, 0xEE, 0, 0, 1, 0xF0])


def test_command_sets_both_instance_parts_and_reclaims_with_the_new_name():
    gw = gateway()
    frames = client_frames(gw, ["0ded2300 40 0a 01 00 ee 00 f8 02", "0ded2300 41 03 05 04 02 ff ff ff"])
    assert gw.device.cfg.device_instance == 2 << 3 | 5
    assert messages(frames)[60928] == gw.device.name()


def test_command_sets_an_installation_description():
    gw = gateway()
    frames = client_frames(
        gw,
        [
            "0ded2300 40 14 01 16 f0 01 f8 01",
            "0ded2300 41 01 0d 01 4e 61 76 20",
            "0ded2300 42 73 74 61 74 69 6f 6e",
        ],
    )
    assert gw.device.cfg.installation_description1 == "Nav station"
    assert messages(frames)[126998].startswith(b"\x0d\x01Nav station")


def test_command_out_of_range_is_refused_per_parameter():
    gw = gateway(device_instance=1)
    payload = bytes([1, 0, 0xEE, 0, 0xF8, 2, 3, 9, 77, 1])
    frames = gw.receive(build_can_id(3, 126208, ME, SOURCE), bytes([0x40, 10]) + payload[:6], NOW)
    frames += gw.receive(build_can_id(3, 126208, ME, SOURCE), bytes([0x41]) + payload[6:] + b"\xff" * 3, NOW)
    assert gw.device.cfg.device_instance == 1
    assert messages(frames)[126208] == bytes([2, 0, 0xEE, 0, 0, 2, 3 | 5 << 4])


def test_command_for_another_pgn_is_not_supported():
    gw = gateway()
    frames = gw.receive(build_can_id(3, 126208, ME, SOURCE), bytes([1, 0x14, 0xF2, 1, 0xF8, 0, 0xFF, 0xFF]), NOW)
    assert messages(frames)[126208] == bytes([2, 0x14, 0xF2, 1, 4, 0])


def group_request(gw: Gateway, pgn: int, interval: bytes):
    payload = bytes([0]) + pgn.to_bytes(3, "little") + interval + bytes([0xFF, 0xFF, 0])
    frames = [bytes([0x40, len(payload)]) + payload[:6], bytes([0x41]) + payload[6:].ljust(7, b"\xff")]
    out = []
    for data in frames:
        out += gw.receive(build_can_id(3, 126208, ME, SOURCE), data, NOW)
    return messages(out)


def test_group_request_sends_the_pgn():
    answer = group_request(gateway(), 126996, b"\xff" * 4)
    assert answer[126208][:5] == bytes([2, 0x14, 0xF0, 1, 0]) and 126996 in answer


def test_group_request_refuses_to_change_the_interval():
    """The acknowledge must not claim a change that was not made (0 = stop transmitting)."""
    gw = gateway()
    gw.poll(NOW, {"gnss_time": NOW})
    answer = group_request(gw, 126993, bytes(4))
    assert answer[126208][:5] == bytes([2, 0x11, 0xF0, 1, 1 << 4])


def test_group_request_of_an_unknown_pgn():
    assert group_request(gateway(), 65000, b"\xff" * 4)[126208][4] == 1


def test_client_lines_with_and_without_time():
    assert parse_client_line("18ea2300 14 f0 01\r") == (0x18EA2300, bytes([0x14, 0xF0, 0x01]))
    assert parse_client_line("17:33:21.107 T 18EA2300 14 F0 01") == (0x18EA2300, bytes([0x14, 0xF0, 0x01]))
    for bad in ("0", "", "$PDGY,N2NET_OFFLINE", "18ea2300 zz", "YDGW CONFIG"):
        assert parse_client_line(bad) is None


def test_assembler_drops_a_message_with_a_lost_frame():
    a = FastPacketAssembler()
    assert a.add(1, 2, bytes([0x20, 20]) + bytes(6)) is None
    assert a.add(1, 2, bytes([0x22]) + bytes(7)) is None
    assert a.add(1, 2, bytes([0x23]) + bytes(7)) == bytes([0x23]) + bytes(7)  # no message is open


def test_tcp_client_is_identified_and_answered():
    """The whole path: connect, get the identity unasked, send a request, get the answer."""

    async def scenario():
        s = Scenario()
        s.output.udp.enabled = False
        s.output.tcp.host, s.output.tcp.port = "127.0.0.1", 0
        runtime = Runtime(s)
        await runtime.restart_transports()
        port = runtime.tcp._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        first = await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"18ea2340 00 ee 01\r\n")  # 126464: not part of the identity sent on connect
        await writer.drain()
        pgn = None
        while pgn != 126464:
            line = await asyncio.wait_for(reader.readline(), 2)
            pgn = parse_can_id(int(line.split()[2], 16))[1]
        writer.close()
        await runtime.stop()
        return first

    first = asyncio.run(scenario())
    assert parse_can_id(int(first.split()[2], 16))[1] == 60928
