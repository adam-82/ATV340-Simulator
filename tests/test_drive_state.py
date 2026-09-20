from modbus_simulator.drive_state import Drive, DriveState
from modbus_simulator.registers import CmdBits, StatusBits


def cmd(*bits: CmdBits) -> int:
    value = 0
    for bit in bits:
        value |= bit
    return value


def test_default_power_up_state():
    drive = Drive()
    assert drive.state == DriveState.SWITCH_ON_DISABLED
    assert drive.status_word & StatusBits.SWITCHED_ON_DISABLED
    assert not (drive.status_word & StatusBits.VOLTAGE_ENABLED)


def test_cia402_bring_up_sequence_reaches_operation_enabled():
    drive = Drive()

    # Shutdown: enable voltage + quick stop normal, switch-on still 0.
    drive.apply_command_word(cmd(CmdBits.ENABLE_VOLTAGE, CmdBits.QUICK_STOP))
    assert drive.state == DriveState.READY_TO_SWITCH_ON

    # Switch on.
    drive.apply_command_word(
        cmd(CmdBits.SWITCH_ON, CmdBits.ENABLE_VOLTAGE, CmdBits.QUICK_STOP)
    )
    assert drive.state == DriveState.SWITCHED_ON

    # Enable operation.
    drive.apply_command_word(
        cmd(
            CmdBits.SWITCH_ON,
            CmdBits.ENABLE_VOLTAGE,
            CmdBits.QUICK_STOP,
            CmdBits.ENABLE_OPERATION,
        )
    )
    assert drive.state == DriveState.OPERATION_ENABLED
    assert drive.status_word & StatusBits.OPERATION_ENABLED


def _bring_up(drive: Drive) -> None:
    drive.apply_command_word(
        cmd(
            CmdBits.SWITCH_ON,
            CmdBits.ENABLE_VOLTAGE,
            CmdBits.QUICK_STOP,
            CmdBits.ENABLE_OPERATION,
        )
    )


def test_speed_ramps_toward_setpoint_over_multiple_ticks():
    drive = Drive(ramp_hz_per_s=10.0)
    _bring_up(drive)
    drive.set_speed_reference(25.0)

    drive.tick(1.0)
    assert drive.output_freq_hz == 10.0
    drive.tick(1.0)
    assert drive.output_freq_hz == 20.0
    drive.tick(1.0)
    assert drive.output_freq_hz == 25.0  # clamps at setpoint, doesn't overshoot
    drive.tick(1.0)
    assert drive.output_freq_hz == 25.0


def test_fault_injection_forces_fault_state_and_zeroes_output():
    drive = Drive()
    _bring_up(drive)
    drive.set_speed_reference(30.0)
    drive.tick(5.0)
    assert drive.output_freq_hz > 0

    drive.inject_fault(9)  # OCF
    assert drive.state == DriveState.FAULT
    assert drive.fault_code == 9
    assert drive.output_freq_hz == 0.0
    assert drive.status_word & StatusBits.FAULT

    drive.tick(1.0)
    assert drive.output_freq_hz == 0.0  # stays at zero while faulted


def test_fault_reset_gated_on_reset_bit():
    drive = Drive()
    _bring_up(drive)
    drive.inject_fault(9)

    # A command word without the fault-reset bit must not clear the fault.
    drive.apply_command_word(cmd(CmdBits.ENABLE_VOLTAGE, CmdBits.QUICK_STOP))
    assert drive.state == DriveState.FAULT

    # 0 -> 1 transition on the fault-reset bit clears it.
    drive.apply_command_word(
        cmd(CmdBits.ENABLE_VOLTAGE, CmdBits.QUICK_STOP, CmdBits.FAULT_RESET)
    )
    assert drive.state == DriveState.SWITCH_ON_DISABLED
    assert drive.fault_code == 0


def test_console_reset_fault_helper():
    drive = Drive()
    _bring_up(drive)
    drive.inject_fault(17)
    drive.reset_fault()
    assert drive.state == DriveState.SWITCH_ON_DISABLED
    assert drive.fault_code == 0


def test_digital_input_bit_set_and_read():
    drive = Drive()
    drive.set_digital_input(0, True)
    assert drive.digital_inputs == 0b1
    drive.set_digital_input(2, True)
    assert drive.digital_inputs == 0b101
    drive.set_digital_input(0, False)
    assert drive.digital_inputs == 0b100


def test_digital_output_write_reflected():
    drive = Drive()
    drive.set_digital_output(0b11)
    assert drive.digital_outputs == 0b11


def test_analog_input_output_round_trip():
    drive = Drive()
    drive.set_analog_input(0, 2500)
    drive.set_analog_input(1, -100)
    assert drive.analog_inputs == [2500, -100]

    drive.set_analog_output(0, 1234)
    assert drive.analog_outputs == [1234]
