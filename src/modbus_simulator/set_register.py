"""Standalone Modbus TCP client for writing a single ATV340 register.

Named `set_register` (not `set`) to avoid shadowing the builtin. A real
Modbus client -- usable against this simulator or a real ATV340 drive.
"""

import argparse
import sys

from .mbclient import add_connection_args, connect, parse_value, register_address, register_label, resolve_register


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modbus-set",
        description="Write a single ATV340 register over Modbus TCP.",
    )
    add_connection_args(parser)
    parser.add_argument(
        "register",
        help="Register to write: a friendly name (speed_ref), a vendor code (lfr), "
        "or a raw address (8502, 0x2136)",
    )
    parser.add_argument("value", help="Value to write (e.g. 25.0 for a Hz register, OCF for a fault, 0x0006 raw)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        register = resolve_register(args.register)
        raw = parse_value(register, args.value)
    except (LookupError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        client = connect(args.host, args.port)
    except ConnectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        result = client.write_register(register_address(register), raw, device_id=args.slave_id)
        if result.isError():
            print(f"error: write failed for {register_label(register)}: {result}", file=sys.stderr)
            raise SystemExit(1)
        print(f"{register_label(register)} <- {args.value}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
