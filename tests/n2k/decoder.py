"""Independent minimal N2K decoder for tests: YD RAW lines -> messages -> field dicts."""

from __future__ import annotations

import struct

NA = object()  # marker not used outside; None means "not available"

FAST = {127489, 128275, 129029, 129540}

# (name, offset, struct code or 'u24', scale)
TABLES: dict[int, list[tuple[str, int, str, float]]] = {
    126992: [("sid", 0, "B", 1), ("source", 1, "B", 1), ("date", 2, "H", 1), ("time", 4, "I", 1e-4)],
    129033: [("date", 0, "H", 1), ("time", 2, "I", 1e-4), ("offset", 6, "h", 1)],
    127245: [("instance", 0, "B", 1), ("order", 2, "h", 1e-4), ("position", 4, "h", 1e-4)],
    127250: [("sid", 0, "B", 1), ("heading", 1, "H", 1e-4), ("deviation", 3, "h", 1e-4),
             ("variation", 5, "h", 1e-4), ("ref_byte", 7, "B", 1)],
    127251: [("sid", 0, "B", 1), ("rate", 1, "i", 3.125e-8)],
    127257: [("sid", 0, "B", 1), ("yaw", 1, "h", 1e-4), ("pitch", 3, "h", 1e-4), ("roll", 5, "h", 1e-4)],
    127258: [("sid", 0, "B", 1), ("source", 1, "B", 1), ("age", 2, "H", 1), ("variation", 4, "h", 1e-4)],
    127488: [("instance", 0, "B", 1), ("rpm", 1, "H", 0.25), ("boost", 3, "H", 100), ("trim", 5, "b", 1)],
    127489: [("instance", 0, "B", 1), ("oil_pressure", 1, "H", 100), ("oil_temp", 3, "H", 0.1),
             ("coolant_temp", 5, "H", 0.01), ("alternator", 7, "h", 0.01), ("fuel_rate", 9, "h", 0.1),
             ("hours", 11, "I", 1), ("coolant_pressure", 15, "H", 100), ("fuel_pressure", 17, "H", 1000),
             ("status1", 20, "H", 1), ("status2", 22, "H", 1), ("load", 24, "b", 1), ("torque", 25, "b", 1)],
    127505: [("level", 1, "h", 0.004), ("capacity", 3, "I", 0.1)],
    127508: [("instance", 0, "B", 1), ("voltage", 1, "h", 0.01), ("current", 3, "h", 0.1),
             ("temp", 5, "H", 0.01), ("sid", 7, "B", 1)],
    128259: [("sid", 0, "B", 1), ("stw", 1, "H", 0.01), ("sog", 3, "H", 0.01), ("ref", 5, "B", 1)],
    128267: [("sid", 0, "B", 1), ("depth", 1, "I", 0.01), ("offset", 5, "h", 0.001), ("range", 7, "B", 1)],
    128275: [("date", 0, "H", 1), ("time", 2, "I", 1e-4), ("log", 6, "I", 1), ("trip", 10, "I", 1)],
    129025: [("lat", 0, "i", 1e-7), ("lon", 4, "i", 1e-7)],
    129026: [("sid", 0, "B", 1), ("ref", 1, "B", 1), ("cog", 2, "H", 1e-4), ("sog", 4, "H", 0.01)],
    129029: [("sid", 0, "B", 1), ("date", 1, "H", 1), ("time", 3, "I", 1e-4), ("lat", 7, "q", 1e-16),
             ("lon", 15, "q", 1e-16), ("altitude", 23, "q", 1e-6), ("type_method", 31, "B", 1),
             ("integrity", 32, "B", 1), ("sats", 33, "B", 1), ("hdop", 34, "h", 0.01),
             ("pdop", 36, "h", 0.01), ("geoid", 38, "i", 0.01), ("refstations", 42, "B", 1)],
    129291: [("sid", 0, "B", 1), ("ref", 1, "B", 1), ("set", 2, "H", 1e-4), ("drift", 4, "H", 0.01)],
    129539: [("sid", 0, "B", 1), ("mode", 1, "B", 1), ("hdop", 2, "h", 0.01), ("vdop", 4, "h", 0.01),
             ("tdop", 6, "h", 0.01)],
    130306: [("sid", 0, "B", 1), ("speed", 1, "H", 0.01), ("angle", 3, "H", 1e-4), ("ref_byte", 5, "B", 1)],
    130310: [("sid", 0, "B", 1), ("water_temp", 1, "H", 0.01), ("air_temp", 3, "H", 0.01),
             ("pressure", 5, "H", 100.0)],
    130311: [("sid", 0, "B", 1), ("sources", 1, "B", 1), ("temp", 2, "H", 0.01),
             ("humidity", 4, "h", 0.004), ("pressure", 6, "H", 100.0)],
    130312: [("sid", 0, "B", 1), ("instance", 1, "B", 1), ("source", 2, "B", 1), ("temp", 3, "H", 0.01),
             ("set", 5, "H", 0.01)],
    130313: [("sid", 0, "B", 1), ("instance", 1, "B", 1), ("source", 2, "B", 1),
             ("humidity", 3, "h", 0.004), ("set", 5, "h", 0.004)],
    130314: [("sid", 0, "B", 1), ("instance", 1, "B", 1), ("source", 2, "B", 1), ("pressure", 3, "i", 0.1)],
    130316: [("sid", 0, "B", 1), ("instance", 1, "B", 1), ("source", 2, "B", 1), ("temp", 3, "u24", 0.001),
             ("set", 6, "H", 0.1)],
}

_NA_RAW = {"B": 0xFF, "b": 0x7F, "H": 0xFFFF, "h": 0x7FFF, "I": 0xFFFFFFFF, "i": 0x7FFFFFFF,
           "q": 0x7FFFFFFFFFFFFFFF, "u24": 0xFFFFFF}
_SIZE = {"B": 1, "b": 1, "H": 2, "h": 2, "I": 4, "i": 4, "q": 8, "u24": 3}


def read(data: bytes, off: int, code: str, scale: float):
    """Reads one field; returns None for the not-available sentinel (or short data)."""
    size = _SIZE[code]
    if off + size > len(data):
        return None
    chunk = data[off : off + size]
    raw = int.from_bytes(chunk, "little") if code == "u24" else struct.unpack("<" + code, chunk)[0]
    if raw == _NA_RAW[code]:
        return None
    return raw * scale


def decode_fields(pgn: int, data: bytes) -> dict:
    """Decodes a reassembled payload into a name -> value dict (None = not available)."""
    return {n: read(data, o, c, sc) for n, o, c, sc in TABLES.get(pgn, [])}


def decode_wind(data: bytes) -> dict:
    d = decode_fields(130306, data)
    d["reference"] = data[5] & 7
    return d


def decode_127250(data: bytes) -> dict:
    d = decode_fields(127250, data)
    d["reference"] = data[7] & 3
    return d


def decode_129033(data: bytes) -> dict:
    return decode_fields(129033, data)


def decode_127505(data: bytes) -> dict:
    d = decode_fields(127505, data)
    d["instance"], d["fluid"] = data[0] & 0x0F, data[0] >> 4
    return d


def decode_130311(data: bytes) -> dict:
    d = decode_fields(130311, data)
    d["temp_source"], d["humidity_source"] = data[1] & 0x3F, data[1] >> 6
    return d


def decode_129540(data: bytes) -> dict:
    n = data[2]
    sats = []
    for i in range(n):
        o = 3 + 12 * i
        sats.append({
            "prn": data[o],
            "elevation": read(data, o + 1, "h", 1e-4),
            "azimuth": read(data, o + 3, "H", 1e-4),
            "snr": read(data, o + 5, "h", 0.01),
            "residual": read(data, o + 7, "i", 1e-5),
            "status": data[o + 11] & 0x0F,
        })
    return {"sid": data[0], "n": n, "sats": sats, "length": len(data)}


SPECIAL = {130306: decode_wind, 127250: decode_127250, 127505: decode_127505,
           130311: decode_130311, 129540: decode_129540}


def decode_payload(pgn: int, data: bytes) -> dict:
    """Decodes one reassembled payload."""
    return SPECIAL.get(pgn, lambda d: decode_fields(pgn, d))(data)


def parse_id(can_id: int) -> tuple[int, int, int]:
    """Returns (priority, pgn, source) for PDU2 ids and (priority, pgn, source) for 60928."""
    pf = (can_id >> 16) & 0xFF
    dp = (can_id >> 24) & 1
    ps = (can_id >> 8) & 0xFF
    pgn = dp << 16 | pf << 8 | (ps if pf >= 240 else 0)
    return (can_id >> 26) & 7, pgn, can_id & 0xFF


def reassemble(lines: list[str]) -> list[tuple[int, bytes]]:
    """Parses YD RAW lines and reassembles fast packets; returns [(pgn, payload)]."""
    out: list[tuple[int, bytes]] = []
    partial: dict[int, dict] = {}
    for line in lines:
        tok = line.rstrip("\r\n").split(" ")
        can_id = int(tok[2], 16)
        data = bytes(int(t, 16) for t in tok[3:])
        _, pgn, _ = parse_id(can_id)
        if pgn not in FAST:
            out.append((pgn, data))
            continue
        ctr = data[0] & 0x1F
        if ctr == 0:
            partial[pgn] = {"seq": data[0] >> 5, "len": data[1], "buf": bytearray(data[2:]), "next": 1}
        else:
            st = partial[pgn]
            assert data[0] >> 5 == st["seq"] and ctr == st["next"]
            st["buf"] += data[1:]
            st["next"] += 1
        st = partial[pgn]
        if len(st["buf"]) >= st["len"]:
            out.append((pgn, bytes(st["buf"][: st["len"]])))
            del partial[pgn]
    return out
