"""CLI: python -m n2k_sim [--scenario file.json] [--ui-host 127.0.0.1] [--ui-port 8080]"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from n2k_sim.app import Runtime
from n2k_sim.config import Scenario
from n2k_sim.web.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="NMEA 2000 sailing yacht simulator (YD RAW over UDP/TCP)")
    parser.add_argument("--scenario", type=Path, help="scenario JSON to start from")
    parser.add_argument("--ui-host", default="127.0.0.1", help="web UI bind address (default: localhost only)")
    parser.add_argument("--ui-port", type=int, default=8080)
    parser.add_argument("--udp-host", help="UDP target (default 255.255.255.255)")
    parser.add_argument("--udp-port", type=int, help="UDP port (default 2002)")
    parser.add_argument("--tcp-port", type=int, help="TCP server port (default 2223)")
    parser.add_argument("--seed", type=int, help="random seed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scenario = Scenario.load(args.scenario) if args.scenario else Scenario()
    if args.udp_host:
        scenario.output.udp.host = args.udp_host
    if args.udp_port:
        scenario.output.udp.port = args.udp_port
    if args.tcp_port:
        scenario.output.tcp.port = args.tcp_port
    if args.seed is not None:
        scenario.seed = args.seed

    out = scenario.output
    print(
        f"n2k-sim: UI http://{args.ui_host}:{args.ui_port}/  ·  YD RAW UDP {out.udp.host}:{out.udp.port}"
        f"  ·  TCP {out.tcp.host}:{out.tcp.port}"
    )
    uvicorn.run(create_app(Runtime(scenario)), host=args.ui_host, port=args.ui_port, log_level="warning")


if __name__ == "__main__":
    main()
