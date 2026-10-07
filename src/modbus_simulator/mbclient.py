"""Shared helpers for the standalone Modbus TCP commissioning tools.

`poll.py` and `set_register.py` are real Modbus TCP clients -- separate
processes from the simulator, talking over the wire like a PLC or a
commissioning laptop would. This module holds the register-name resolution
and value encode/decode logic they share, kept out of `registers.py` so the
register map itself stays pure vendor data with no CLI/UX concerns mixed in.
"""

import argparse

from pymodbus.client import ModbusTcpClient

from .registers import (
    ANALOG_INPUT_1,
    ANALOG_INPUT_2,
    ANALOG_OUTPUT_1,
    CMD_WORD,
    DIGITAL_INPUTS,
    DIGITAL_OUTPUTS,
    FAULT_NAMES,
    FAULT_WORD,
    OUTPUT_FREQ,
    SPEED_REF,
    STATUS_WORD,
    ALL_REGISTERS,
    CmdBits,
    DigitalInputBits,
    DigitalOutputBits,
    FAULT_CODES,
    Register,
    StatusBits,
    from_u16,
    to_u16,
)

# Friendlier snake_case aliases, in addition to each register's vendor code
# (e.g. "lfr"), which is registered automatically below.
_FRIENDLY_ALIASES: dict[str, Register] = {
    "cmd_word": CMD_WORD,
    "status_word": STATUS_WORD,
    "speed_ref": SPEED_REF,
    "output_freq": OUTPUT_FREQ,
    "fault_word": FAULT_WORD,
    "digital_inputs": DIGITAL_INPUTS,
    "digital_outputs": DIGITAL_OUTPUTS,
    "analog_input_1": ANALOG_INPUT_1,
    "analog_input_2": ANALOG_INPUT_2,
    "analog_output_1": ANALOG_OUTPUT_1,
}

REGISTER_ALIASES: dict[str, Register] = {
    **{register.name.lower(): register for register in ALL_REGISTERS},
    **_FRIENDLY_ALIASES,
}

_HZ_REGISTERS = {SPEED_REF, OUTPUT_FREQ}


def resolve_register(token: str) -> Register | int:
    """Resolve a user-typed register token to a known `Register` or a raw address.

    Accepts a friendly name (`speed_ref`), a vendor code (`lfr`), both
    case-insensitively, or a raw numeric Modbus address (`8502`, `0x2136`)
    for anything not in the map.
    """
    register = REGISTER_ALIASES.get(token.lower())
    if register is not None:
        return register
    try:
        return int(token, 0)
    except ValueError:
        raise LookupError(f"unknown register {token!r}") from None


def register_address(register: Register | int) -> int:
    return register.address if isinstance(register, Register) else register


def register_label(register: Register | int) -> str:
    return register.name if isinstance(register, Register) else f"0x{register:04X}"


def _flag_name(flags) -> str:
    # IntFlag.__str__ prints the bare int since Python 3.11; .name gives the
    # pipe-joined member names we actually want for display.
    return flags.name or "0"


def format_value(register: Register | int, raw: int) -> str:
    """Pretty-print a raw 16-bit register value for display."""
    if register == CMD_WORD:
        return f"{_flag_name(CmdBits(raw))} (0x{raw:04X})"
    if register == STATUS_WORD:
        return f"{_flag_name(StatusBits(raw))} (0x{raw:04X})"
    if register == FAULT_WORD:
        return f"{raw} ({FAULT_CODES.get(raw, 'unknown')})"
    if register in _HZ_REGISTERS:
        return f"{from_u16(raw) / 10.0:.1f} Hz"
    if register == DIGITAL_INPUTS:
        return f"{_flag_name(DigitalInputBits(raw & 0x3F))} (0x{raw:04X})"
    if register == DIGITAL_OUTPUTS:
        return f"{_flag_name(DigitalOutputBits(raw & 0x103))} (0x{raw:04X})"
    return str(from_u16(raw))


def parse_value(register: Register | int, text: str) -> int:
    """Parse a user-typed value into the raw unsigned 16-bit value to write."""
    if register == FAULT_WORD:
        if text.isdigit():
            return to_u16(int(text))
        code = FAULT_NAMES.get(text.upper())
        if code is None:
            raise ValueError(f"unknown fault name {text!r}")
        return to_u16(code)
    if register in _HZ_REGISTERS:
        return to_u16(round(float(text) * 10))
    return to_u16(int(text, 0))


def connect(host: str, port: int) -> ModbusTcpClient:
    """Connect a `ModbusTcpClient`, raising `ConnectionError` on failure."""
    client = ModbusTcpClient(host, port=port)
    if not client.connect():
        raise ConnectionError(f"could not connect to {host}:{port}")
    return client


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="Modbus server address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5020, help="Modbus TCP port (default: 5020)")
    parser.add_argument("--slave-id", type=int, default=0, help="Modbus device/slave id (default: 0)")
