import time

import pytest
from pymodbus.client import ModbusTcpClient

from modbus_simulator.drive_state import Drive
from modbus_simulator.registers import (
    ANALOG_INPUT_1,
    ANALOG_OUTPUT_1,
    CMD_WORD,
    DIGITAL_INPUTS,
    DIGITAL_OUTPUTS,
    FAULT_WORD,
    OUTPUT_FREQ,
    SPEED_REF,
    STATUS_WORD,
    CmdBits,
    StatusBits,
    from_u16,
    to_u16,
)
from modbus_simulator.server import start_server_thread

DEVICE_ID = 0
_next_port = iter(range(15020, 15020 + 100))


@pytest.fixture
def drive_and_client():
    port = next(_next_port)
    drive = Drive(ramp_hz_per_s=100.0)
    _thread, stop = start_server_thread("127.0.0.1", port, drive, slave_id=DEVICE_ID)
    client = ModbusTcpClient("127.0.0.1", port=port)
    assert client.connect()
    try:
        yield drive, client
    finally:
        client.close()
        stop()


def _write(client, register, value):
    result = client.write_register(register.address, value, device_id=DEVICE_ID)
    assert not result.isError(), result
    return result


def _read(client, register):
    result = client.read_holding_registers(register.address, count=1, device_id=DEVICE_ID)
    assert not result.isError(), result
    return result.registers[0]


def _bring_up(client):
    cmd = CmdBits.ENABLE_VOLTAGE | CmdBits.QUICK_STOP
    _write(client, CMD_WORD, cmd)
    cmd |= CmdBits.SWITCH_ON
    _write(client, CMD_WORD, cmd)
    cmd |= CmdBits.ENABLE_OPERATION
    _write(client, CMD_WORD, cmd)


def test_status_word_after_bring_up(drive_and_client):
    _drive, client = drive_and_client
    _bring_up(client)
    status = _read(client, STATUS_WORD)
    assert status & StatusBits.OPERATION_ENABLED


def test_speed_reference_ramps_output_frequency(drive_and_client):
    _drive, client = drive_and_client
    _bring_up(client)
    _write(client, SPEED_REF, to_u16(300))  # 30.0 Hz

    last_freq = 0.0
    for _ in range(5):
        time.sleep(0.05)
        freq = from_u16(_read(client, OUTPUT_FREQ)) / 10.0
        assert freq >= last_freq
        last_freq = freq
    assert last_freq > 0.0


def test_fault_and_reset_via_registers(drive_and_client):
    drive, client = drive_and_client
    _bring_up(client)

    drive.inject_fault(9)
    status = _read(client, STATUS_WORD)
    assert status & StatusBits.FAULT
    assert _read(client, FAULT_WORD) == 9

    # Fault reset requires the reset bit transition on the command word.
    cmd = CmdBits.ENABLE_VOLTAGE | CmdBits.QUICK_STOP | CmdBits.FAULT_RESET
    _write(client, CMD_WORD, cmd)
    status = _read(client, STATUS_WORD)
    assert not (status & StatusBits.FAULT)
    assert _read(client, FAULT_WORD) == 0


def test_digital_input_set_via_drive_read_via_modbus(drive_and_client):
    drive, client = drive_and_client
    drive.set_digital_input(1, True)
    assert _read(client, DIGITAL_INPUTS) == 0b10


def test_digital_output_write_via_modbus_reflected_in_drive(drive_and_client):
    drive, client = drive_and_client
    _write(client, DIGITAL_OUTPUTS, 0b101)
    assert drive.digital_outputs == 0b101


def test_analog_input_set_via_drive_read_via_modbus(drive_and_client):
    drive, client = drive_and_client
    drive.set_analog_input(0, 4321)
    assert from_u16(_read(client, ANALOG_INPUT_1)) == 4321


def test_analog_output_write_via_modbus_reflected_in_drive(drive_and_client):
    drive, client = drive_and_client
    _write(client, ANALOG_OUTPUT_1, to_u16(-500))
    assert drive.analog_outputs[0] == -500
