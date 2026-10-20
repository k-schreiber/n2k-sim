"""Field packers, CAN ids, fast-packet framing and YD RAW grammar."""

from __future__ import annotations

import math
import re

import pytest

from n2k_sim.formats.ydraw import format_frame, frames_to_bytes, parse_line
from n2k_sim.n2k import fields as f
from n2k_sim.n2k.canid import build_can_id, parse_can_id
from n2k_sim.n2k.fastpacket import FastPacketFramer, frame_count, split_fast_packet
from n2k_sim.n2k.types import CanFrame


def test_sentinels():
    assert f.u8(None) == b"\xff"
    assert f.u16(None) == b"\xff\xff"
    assert f.i16(None) == b"\xff\x7f"
    assert f.u24(None) == b"\xff\xff\xff"
    assert f.u32(None) == b"\xff" * 4
    assert f.i32(None) == b"\xff\xff\xff\x7f"
    assert f.i64(None) == b"\xff" * 7 + b"\x7f"
    assert f.u16(float("nan")) == b"\xff\xff"
    assert f.reserved(3) == b"\xff\xff\xff"


def test_rounding_and_clamping():
    assert f.u16(1.2345, 0.0001) == (12345).to_bytes(2, "little")
    assert f.i16(-0.5, 0.01) == (-50).to_bytes(2, "little", signed=True)
    assert f.u16(-5) == b"\x00\x00"
    assert int.from_bytes(f.u16(1e9), "little") < 0xFFFD
    assert int.from_bytes(f.i16(1e9), "little", signed=True) < 0x7FFD
    assert int.from_bytes(f.i16(-1e9), "little", signed=True) == -0x8000
    assert f.u24(1.0, 0.001) == (1000).to_bytes(3, "little")
    assert f.i32(-1, 1e-7) == (-10_000_000).to_bytes(4, "little", signed=True)


def test_angles_speed_temp():
    assert f.angle_u16(-math.pi / 2) == (47124).to_bytes(2, "little")  # wrapped to 3π/2
    assert f.angle_u16(0.0) == b"\x00\x00"
    assert f.angle_i16(math.pi * 1.5) == (-15708).to_bytes(2, "little", signed=True)
    assert f.angle_i16(None) == b"\xff\x7f"
    assert f.speed_u16(3.456) == (346).to_bytes(2, "little")
    assert f.temp_u16_K(288.15) == (28815).to_bytes(2, "little")


def test_date_time():
    epoch = 1_700_000_000.5  # 2023-11-14 22:13:20.5 UTC
    assert int.from_bytes(f.date_u16(epoch), "little") == 19675
    assert int.from_bytes(f.time_u32(epoch), "little") == (22 * 3600 + 13 * 60 + 20) * 10000 + 5000
    assert f.date_u16(None) == b"\xff\xff"
    assert f.time_u32(None) == b"\xff" * 4


def test_can_id_example():
    assert build_can_id(2, 130306, 0x23) == 0x09FD0223
    assert parse_can_id(0x09FD0223) == (2, 130306, 0x23, 0xFF)


@pytest.mark.parametrize("prio,pgn,src", [(3, 126992, 1), (7, 127258, 254), (6, 129029, 0x23)])
def test_can_id_round_trip_pdu2(prio, pgn, src):
    assert parse_can_id(build_can_id(prio, pgn, src)) == (prio, pgn, src, 0xFF)


def test_can_id_pdu1():
    can_id = build_can_id(6, 60928, 0x23)  # destination defaults to global
    assert can_id == 0x18EEFF23
    assert parse_can_id(can_id) == (6, 60928, 0x23, 0xFF)
    assert parse_can_id(build_can_id(6, 60928, 0x23, 0x10)) == (6, 60928, 0x23, 0x10)
    with pytest.raises(ValueError):
        build_can_id(8, 1, 1)


def test_fast_packet_frame_counts():
    assert frame_count(14) == 3 and frame_count(43) == 7 and frame_count(26) == 4
    assert len(split_fast_packet(bytes(range(14)), 0)) == 3
    assert len(split_fast_packet(bytes(range(43)), 0)) == 7
    assert frame_count(3) == 1 and frame_count(6) == 1 and frame_count(7) == 2


def test_fast_packet_content():
    payload = bytes(range(14))
    frames = split_fast_packet(payload, 5)
    assert frames[0] == bytes([0xA0, 14]) + payload[:6]
    assert frames[1] == bytes([0xA1]) + payload[6:13]
    assert frames[2] == bytes([0xA2, 13]) + b"\xff" * 6
    assert all(len(x) == 8 for x in frames)


def test_sequence_counter_per_pgn():
    fr = FastPacketFramer()
    seqs = [fr.frames(129029, bytes(43))[0][0] >> 5 for _ in range(10)]
    assert seqs == [0, 1, 2, 3, 4, 5, 6, 7, 0, 1]
    assert fr.frames(128275, bytes(14))[0][0] >> 5 == 0  # independent counter
    for frame in fr.frames(129029, bytes(43)):
        assert frame[0] >> 5 == 2  # constant within a message


def test_single_frame_padding():
    fr = FastPacketFramer()
    assert fr.frames(129025, b"\x01\x02", fast_packet=False) == [b"\x01\x02" + b"\xff" * 6]
    with pytest.raises(ValueError):
        fr.frames(129025, bytes(9), fast_packet=False)


LINE = re.compile(r"^\d\d:\d\d:\d\d\.\d{3} R [0-9A-F]{8}( [0-9A-F]{2}){1,8}\r\n$")


def test_ydraw_line():
    frame = CanFrame(0x09FD0223, bytes([0, 0x6A, 1, 0x5C, 0x3A, 0xFA, 0xFF, 0xFF]), 1_700_000_000.1234)
    line = format_frame(frame)
    assert line == "22:13:20.123 R 09FD0223 00 6A 01 5C 3A FA FF FF\r\n"
    assert LINE.match(line)
    assert parse_line(line) == (0x09FD0223, frame.data)
    assert frames_to_bytes([frame, frame]) == (line * 2).encode()


def test_ydraw_millisecond_does_not_overflow():
    line = format_frame(CanFrame(1, b"\x00", 59.9996))
    assert line.startswith("00:00:59.999 R 00000001 00")


@pytest.mark.parametrize("bad", ["", "00:00:00.000 T 00000001 00", "00:00:00.000 R 00000001",
                                 "00:00:00.000  R 00000001 00", "00:00:00.000 R 00000001 0", "x R 1 00"])
def test_parse_line_rejects(bad):
    with pytest.raises(ValueError):
        parse_line(bad)
