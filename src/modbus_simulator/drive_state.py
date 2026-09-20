"""Pure drive-state logic for the ATV340 simulator (no Modbus/I-O dependencies).

Models the CiA 402 state machine used by Schneider Altivar drives, plus
speed ramping, fault handling, and the digital/analog I/O the simulator
exposes over Modbus.
"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto

from .registers import CmdBits, StatusBits


class DriveState(Enum):
    SWITCH_ON_DISABLED = auto()
    READY_TO_SWITCH_ON = auto()
    SWITCHED_ON = auto()
    OPERATION_ENABLED = auto()
    QUICK_STOP_ACTIVE = auto()
    FAULT = auto()


def _compute_state(
    switch_on: bool, enable_voltage: bool, quick_stop: bool, enable_operation: bool
) -> DriveState:
    if not enable_voltage:
        return DriveState.SWITCH_ON_DISABLED
    if not quick_stop:
        return DriveState.QUICK_STOP_ACTIVE
    if not switch_on:
        return DriveState.READY_TO_SWITCH_ON
    if not enable_operation:
        return DriveState.SWITCHED_ON
    return DriveState.OPERATION_ENABLED


def _status_word_for_state(state: DriveState) -> int:
    bits = StatusBits(0)
    if state in (
        DriveState.READY_TO_SWITCH_ON,
        DriveState.SWITCHED_ON,
        DriveState.OPERATION_ENABLED,
        DriveState.QUICK_STOP_ACTIVE,
    ):
        bits |= StatusBits.READY_TO_SWITCH_ON
    if state in (DriveState.SWITCHED_ON, DriveState.OPERATION_ENABLED):
        bits |= StatusBits.SWITCHED_ON
    if state == DriveState.OPERATION_ENABLED:
        bits |= StatusBits.OPERATION_ENABLED
    if state == DriveState.FAULT:
        bits |= StatusBits.FAULT
    if state != DriveState.SWITCH_ON_DISABLED:
        bits |= StatusBits.VOLTAGE_ENABLED
    if state != DriveState.QUICK_STOP_ACTIVE:
        bits |= StatusBits.QUICK_STOP
    if state == DriveState.SWITCH_ON_DISABLED:
        bits |= StatusBits.SWITCHED_ON_DISABLED
    bits |= StatusBits.REMOTE
    if state == DriveState.OPERATION_ENABLED:
        bits |= StatusBits.TARGET_REACHED
    return int(bits)


@dataclass
class Drive:
    ramp_hz_per_s: float = 10.0

    state: DriveState = DriveState.SWITCH_ON_DISABLED
    command_word: int = 0
    status_word: int = field(init=False, default=0)
    speed_ref_hz: float = 0.0
    output_freq_hz: float = 0.0
    fault_code: int = 0

    digital_inputs: int = 0
    digital_outputs: int = 0
    analog_inputs: list[int] = field(default_factory=lambda: [0, 0])
    analog_outputs: list[int] = field(default_factory=lambda: [0])

    _prev_fault_reset_bit: bool = field(default=False, repr=False)
    _last_update: float = field(default_factory=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        self.status_word = _status_word_for_state(self.state)

    def apply_command_word(self, cmd: int) -> None:
        cmd &= 0xFFFF
        self.command_word = cmd
        switch_on = bool(cmd & CmdBits.SWITCH_ON)
        enable_voltage = bool(cmd & CmdBits.ENABLE_VOLTAGE)
        quick_stop = bool(cmd & CmdBits.QUICK_STOP)
        enable_operation = bool(cmd & CmdBits.ENABLE_OPERATION)
        fault_reset = bool(cmd & CmdBits.FAULT_RESET)

        if self.state == DriveState.FAULT:
            if fault_reset and not self._prev_fault_reset_bit:
                self.state = DriveState.SWITCH_ON_DISABLED
                self.fault_code = 0
        else:
            self.state = _compute_state(
                switch_on, enable_voltage, quick_stop, enable_operation
            )

        self._prev_fault_reset_bit = fault_reset
        self.status_word = _status_word_for_state(self.state)

    def set_speed_reference(self, hz: float) -> None:
        self.speed_ref_hz = hz

    def tick(self, dt: float) -> None:
        if self.state == DriveState.FAULT:
            self.output_freq_hz = 0.0
            return
        target = (
            self.speed_ref_hz if self.state == DriveState.OPERATION_ENABLED else 0.0
        )
        max_step = self.ramp_hz_per_s * dt
        delta = target - self.output_freq_hz
        if abs(delta) <= max_step:
            self.output_freq_hz = target
        else:
            self.output_freq_hz += max_step if delta > 0 else -max_step

    def tick_realtime(self) -> None:
        now = time.monotonic()
        dt = now - self._last_update
        self._last_update = now
        if dt > 0:
            self.tick(dt)

    def inject_fault(self, code: int) -> None:
        self.fault_code = code
        self.output_freq_hz = 0.0
        self.state = DriveState.FAULT
        self.status_word = _status_word_for_state(self.state)

    def reset_fault(self) -> None:
        if self.state == DriveState.FAULT:
            self.state = DriveState.SWITCH_ON_DISABLED
            self.fault_code = 0
            self.status_word = _status_word_for_state(self.state)

    def set_digital_input(self, bit: int, value: bool) -> None:
        if value:
            self.digital_inputs |= 1 << bit
        else:
            self.digital_inputs &= ~(1 << bit)

    def set_analog_input(self, index: int, value: int) -> None:
        self.analog_inputs[index] = value

    def set_digital_output(self, word: int) -> None:
        self.digital_outputs = word & 0xFFFF

    def set_analog_output(self, index: int, value: int) -> None:
        self.analog_outputs[index] = value
