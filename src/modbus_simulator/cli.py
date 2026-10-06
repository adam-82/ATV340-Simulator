"""Command-line entry point for the ATV340 Modbus TCP simulator."""

import argparse
import logging
import signal
import sys
import threading

from .console import SimulatorConsole
from .drive_state import Drive
from .server import start_server_thread


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modbus-simulator",
        description="Simulate a Schneider Electric ATV340 drive over Modbus TCP.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Address to listen on (default: 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=5020,
        help="TCP port to listen on (default: 5020; use 502 to match a real PLC config, "
        "may require elevated privileges)",
    )
    parser.add_argument("--slave-id", type=int, default=0, help="Modbus device/slave id (default: 0)")
    parser.add_argument(
        "--speed-ramp-hz-per-s",
        type=float,
        default=10.0,
        help="Simulated acceleration/deceleration rate in Hz/s (default: 10.0)",
    )
    parser.add_argument(
        "--initial-speed-ref",
        type=float,
        default=0.0,
        help="Initial speed reference in Hz (default: 0.0)",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Run headless (no interactive console); blocks until Ctrl+C",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level.upper())

    drive = Drive(ramp_hz_per_s=args.speed_ramp_hz_per_s)
    drive.set_speed_reference(args.initial_speed_ref)

    try:
        _thread, stop = start_server_thread(args.host, args.port, drive, slave_id=args.slave_id)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"ATV340 simulator listening on {args.host}:{args.port} (slave id {args.slave_id})")

    if args.no_console:
        stop_event = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
        signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
        stop_event.wait()
    else:
        SimulatorConsole(drive).cmdloop()

    stop()


if __name__ == "__main__":
    main()
