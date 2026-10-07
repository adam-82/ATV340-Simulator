"""Standalone Modbus TCP client for polling ATV340 registers.

A real Modbus client -- usable against this simulator or a real ATV340
drive on the network, since the register map is the real vendor map.
"""

import argparse
import sys
import time

from .mbclient import add_connection_args, connect, format_value, register_address, register_label, resolve_register


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modbus-poll",
        description="Read one or more ATV340 registers over Modbus TCP.",
    )
    add_connection_args(parser)
    parser.add_argument(
        "registers",
        nargs="+",
        help="Register(s) to read: a friendly name (speed_ref), a vendor code (lfr), "
        "or a raw address (8502, 0x2136)",
    )
    parser.add_argument("--watch", action="store_true", help="Poll continuously until Ctrl+C")
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Seconds between reads in --watch mode (default: 1.0)"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        registers = [resolve_register(token) for token in args.registers]
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        client = connect(args.host, args.port)
    except ConnectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        while True:
            for register in registers:
                result = client.read_holding_registers(
                    register_address(register), count=1, device_id=args.slave_id
                )
                if result.isError():
                    print(f"error: read failed for {register_label(register)}: {result}", file=sys.stderr)
                    raise SystemExit(1)
                print(f"{register_label(register)}: {format_value(register, result.registers[0])}")
            if not args.watch:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
