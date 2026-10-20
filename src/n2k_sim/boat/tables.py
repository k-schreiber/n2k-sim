"""Lookup tables of the boat: polar (boat speed) and heel."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from n2k_sim.geo import bilinear

_SPLIT = re.compile(r"[\t;,]+|\s{2,}| ")


@dataclass(frozen=True)
class Polar:
    """Boat speed (kn) by true wind speed (kn, columns) and true wind angle (deg, rows)."""

    name: str
    tws: list[float]
    twa: list[float]
    speed: list[list[float]]

    def boat_speed(self, tws_kn: float, twa_deg: float) -> float:
        return max(bilinear(self.tws, self.twa, self.speed, tws_kn, abs(twa_deg)), 0.0)

    @classmethod
    def parse(cls, text: str, name: str = "polar") -> "Polar":
        """Parses the common .pol format: header `TWA\\TWS<sep>tws…`, then `twa<sep>speeds…`."""
        rows = [
            [c for c in _SPLIT.split(line.strip()) if c]
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(rows) < 2:
            raise ValueError("polar needs a header and at least one row")
        tws = [float(v) for v in rows[0][1:]]
        twa, speed = [], []
        for row in rows[1:]:
            values = [float(v) for v in row]
            if len(values) != len(tws) + 1:
                raise ValueError(f"row for TWA {row[0]} has {len(values) - 1} speeds, expected {len(tws)}")
            twa.append(values[0])
            speed.append(values[1:])
        if not tws or sorted(tws) != tws or sorted(twa) != twa:
            raise ValueError("TWS and TWA must be ascending")
        return cls(name, tws, twa, speed)

    @classmethod
    def load(cls, path: Path) -> "Polar":
        return cls.parse(Path(path).read_text(), Path(path).name)


@dataclass(frozen=True)
class HeelTable:
    """Heel (deg, unsigned) by apparent wind speed (kn, rows) and |AWA| (deg, columns)."""

    aws: list[float]
    awa: list[float]
    heel: list[list[float]]

    def heel_deg(self, aws_kn: float, awa_deg: float) -> float:
        return bilinear(self.awa, self.aws, self.heel, abs(awa_deg), aws_kn)

    @classmethod
    def load(cls, path: Path) -> "HeelTable":
        data = json.loads(Path(path).read_text())
        return cls(data["aws"], data["awa"], data["heel"])
