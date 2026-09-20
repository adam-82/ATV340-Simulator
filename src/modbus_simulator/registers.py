"""ATV340 Modbus register map.

Addresses and bit layouts are sourced from Schneider Electric's official
"ATV340 Communication Parameters" spreadsheet (document reference NVE61728,
version 4.6). The spreadsheet itself is not distributed with this project;
only these extracted values are.
"""

from enum import IntFlag
from typing import NamedTuple


class Register(NamedTuple):
    address: int
    name: str
    description: str


# --- Drive control / status --------------------------------------------------

CMD_WORD = Register(8501, "CMD", "Command register (CiA 402 control word)")
STATUS_WORD = Register(3201, "ETA", "Status register (CiA 402 status word)")
SPEED_REF = Register(8502, "LFR", "Reference frequency setpoint, 0.1 Hz units")
OUTPUT_FREQ = Register(3202, "RFR", "Motor (output) frequency, actual, 0.1 Hz units")
FAULT_WORD = Register(7121, "LFT", "Last fault code (enumeration)")

# --- Digital / analog I/O -----------------------------------------------------

DIGITAL_INPUTS = Register(5202, "IL1R", "Logic inputs real image (bitfield)")
DIGITAL_OUTPUTS = Register(5212, "OL1R", "Logic outputs real image (bitfield)")
ANALOG_INPUT_1 = Register(5232, "AI1R", "Analog input 1 standardized value")
ANALOG_INPUT_2 = Register(5233, "AI2R", "Analog input 2 standardized value")
ANALOG_OUTPUT_1 = Register(5261, "AO1R", "Analog output 1 standardized value")

ALL_REGISTERS = [
    CMD_WORD,
    STATUS_WORD,
    SPEED_REF,
    OUTPUT_FREQ,
    FAULT_WORD,
    DIGITAL_INPUTS,
    DIGITAL_OUTPUTS,
    ANALOG_INPUT_1,
    ANALOG_INPUT_2,
    ANALOG_OUTPUT_1,
]


class CmdBits(IntFlag):
    """CMD (control word) bits, standard CiA 402 profile."""

    SWITCH_ON = 1 << 0
    ENABLE_VOLTAGE = 1 << 1
    QUICK_STOP = 1 << 2  # 0 = quick stop requested, 1 = normal
    ENABLE_OPERATION = 1 << 3
    FAULT_RESET = 1 << 7  # 0 -> 1 transition clears a fault
    HALT = 1 << 8


class StatusBits(IntFlag):
    """ETA (status word) bits, standard CiA 402 profile."""

    READY_TO_SWITCH_ON = 1 << 0
    SWITCHED_ON = 1 << 1
    OPERATION_ENABLED = 1 << 2
    FAULT = 1 << 3
    VOLTAGE_ENABLED = 1 << 4
    QUICK_STOP = 1 << 5  # 0 = quick stop active, 1 = normal
    SWITCHED_ON_DISABLED = 1 << 6
    WARNING = 1 << 7
    REMOTE = 1 << 9
    TARGET_REACHED = 1 << 10
    INTERNAL_LIMIT_ACTIVE = 1 << 11


class DigitalInputBits(IntFlag):
    """IL1R bits actually present on a base ATV340 (LI1-LI6)."""

    LI1 = 1 << 0
    LI2 = 1 << 1
    LI3 = 1 << 2
    LI4 = 1 << 3
    LI5 = 1 << 4
    LI6 = 1 << 5


class DigitalOutputBits(IntFlag):
    """OL1R bits actually present on a base ATV340 (R1, R2 relays + DO1)."""

    R1 = 1 << 0
    R2 = 1 << 1
    DO1 = 1 << 8


# LFT fault code enumeration (representative subset; full list has ~80 codes
# and more can be added straight from the source spreadsheet if needed).
FAULT_CODES: dict[int, str] = {
    0: "NOF",  # No error detected
    9: "OCF",  # Overcurrent
    16: "OHF",  # Device overheating
    17: "OLF",  # Motor overload
    18: "OBF",  # DC bus overvoltage
    19: "OSF",  # Supply mains overvoltage
    22: "USF",  # Supply mains undervoltage
    23: "SCF1",  # Motor short circuit
    24: "SOF",  # Motor overspeed
}

FAULT_NAMES: dict[str, int] = {name: code for code, name in FAULT_CODES.items()}


def to_u16(value: int) -> int:
    """Encode a signed 16-bit value as its raw unsigned Modbus register value."""
    return value & 0xFFFF


def from_u16(value: int) -> int:
    """Decode a raw unsigned Modbus register value as a signed 16-bit int."""
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value
