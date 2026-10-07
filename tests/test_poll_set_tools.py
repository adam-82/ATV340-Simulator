import pytest

from modbus_simulator import poll, set_register
from modbus_simulator.drive_state import Drive
from modbus_simulator.server import start_server_thread

DEVICE_ID = 0
_next_port = iter(range(15200, 15200 + 100))


@pytest.fixture
def drive_and_port():
    port = next(_next_port)
    drive = Drive(ramp_hz_per_s=100.0)
    _thread, stop = start_server_thread("127.0.0.1", port, drive, slave_id=DEVICE_ID)
    try:
        yield drive, port
    finally:
        stop()


def _args(port: int, *rest: str) -> list[str]:
    return ["--host", "127.0.0.1", "--port", str(port), "--slave-id", str(DEVICE_ID), *rest]


def test_poll_reads_register_by_friendly_name(drive_and_port, capsys):
    drive, port = drive_and_port
    drive.set_speed_reference(25.0)

    poll.main(_args(port, "speed_ref"))

    out = capsys.readouterr().out
    assert "LFR" in out
    assert "25.0 Hz" in out


def test_poll_reads_register_by_vendor_code(drive_and_port, capsys):
    drive, port = drive_and_port
    drive.set_speed_reference(12.5)

    poll.main(_args(port, "lfr"))

    out = capsys.readouterr().out
    assert "LFR" in out
    assert "12.5 Hz" in out


def test_poll_reads_register_by_raw_address(drive_and_port, capsys):
    drive, port = drive_and_port
    drive.set_digital_input(1, True)

    poll.main(_args(port, "5202"))  # DIGITAL_INPUTS address

    out = capsys.readouterr().out
    assert "0x1452" in out


def test_poll_reads_multiple_registers(drive_and_port, capsys):
    _drive, port = drive_and_port

    poll.main(_args(port, "status_word", "cmd_word"))

    out = capsys.readouterr().out
    assert "ETA" in out
    assert "CMD" in out


def test_set_writes_register_and_poll_reads_it_back(drive_and_port, capsys):
    _drive, port = drive_and_port

    set_register.main(_args(port, "speed_ref", "40.0"))
    capsys.readouterr()

    poll.main(_args(port, "speed_ref"))
    out = capsys.readouterr().out
    assert "40.0 Hz" in out


def test_set_unknown_register_fails_cleanly(drive_and_port, capsys):
    _drive, port = drive_and_port

    with pytest.raises(SystemExit) as exc_info:
        set_register.main(_args(port, "not_a_register", "1"))

    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "unknown register" in err


def test_poll_unknown_register_fails_cleanly(drive_and_port, capsys):
    _drive, port = drive_and_port

    with pytest.raises(SystemExit) as exc_info:
        poll.main(_args(port, "not_a_register"))

    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "unknown register" in err


def test_poll_connection_refused_fails_cleanly(capsys):
    closed_port = next(_next_port)

    with pytest.raises(SystemExit) as exc_info:
        poll.main(_args(closed_port, "speed_ref"))

    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "could not connect" in err
