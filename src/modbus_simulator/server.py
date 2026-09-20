"""Wires the ATV340 Drive state machine to a pymodbus TCP server.

pymodbus 3.15 replaced the classic ModbusSlaveContext/DataBlock override
pattern with a declarative SimData/SimDevice model plus a single per-device
`action` callback invoked on every register access (read or write). This
module uses that callback as the sync point between the Modbus wire format
and the in-memory `Drive` state machine: on every access it applies any
incoming write to the relevant `Drive` method, advances the drive's
simulated time (`tick_realtime`), and republishes the drive's current state
into the register block before the response is sent.
"""

import asyncio
import threading
from collections.abc import Callable

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import SimData, SimDevice
from pymodbus.simulator.simdata import DataType

from . import registers as regs
from .drive_state import Drive


def _build_simdata() -> list[SimData]:
    return [
        SimData(address=register.address, datatype=DataType.REGISTERS)
        for register in regs.ALL_REGISTERS
    ]


def _make_action(drive: Drive) -> Callable:
    async def action(function_code, start_address, address, count, current_registers, set_values):
        if set_values:
            for i, value in enumerate(set_values):
                addr = address + i
                if addr == regs.CMD_WORD.address:
                    drive.apply_command_word(value)
                elif addr == regs.SPEED_REF.address:
                    drive.set_speed_reference(regs.from_u16(value) / 10.0)
                elif addr == regs.DIGITAL_OUTPUTS.address:
                    drive.set_digital_output(value)
                elif addr == regs.ANALOG_OUTPUT_1.address:
                    drive.set_analog_output(0, regs.from_u16(value))

        drive.tick_realtime()

        def offset(addr: int) -> int:
            return addr - start_address

        current_registers[offset(regs.CMD_WORD.address)] = drive.command_word
        current_registers[offset(regs.STATUS_WORD.address)] = drive.status_word
        current_registers[offset(regs.SPEED_REF.address)] = regs.to_u16(
            round(drive.speed_ref_hz * 10)
        )
        current_registers[offset(regs.OUTPUT_FREQ.address)] = regs.to_u16(
            round(drive.output_freq_hz * 10)
        )
        current_registers[offset(regs.FAULT_WORD.address)] = drive.fault_code
        current_registers[offset(regs.DIGITAL_INPUTS.address)] = drive.digital_inputs
        current_registers[offset(regs.DIGITAL_OUTPUTS.address)] = drive.digital_outputs
        current_registers[offset(regs.ANALOG_INPUT_1.address)] = regs.to_u16(
            drive.analog_inputs[0]
        )
        current_registers[offset(regs.ANALOG_INPUT_2.address)] = regs.to_u16(
            drive.analog_inputs[1]
        )
        current_registers[offset(regs.ANALOG_OUTPUT_1.address)] = regs.to_u16(
            drive.analog_outputs[0]
        )
        return None

    return action


def build_device(drive: Drive, slave_id: int = 0) -> SimDevice:
    return SimDevice(id=slave_id, simdata=_build_simdata(), action=_make_action(drive))


def start_server_thread(
    host: str, port: int, drive: Drive, slave_id: int = 0
) -> tuple[threading.Thread, Callable[[], None]]:
    """Start the Modbus TCP server on a background thread.

    Returns the thread and a `stop()` callable that cleanly shuts the
    server down (safe to call from a different thread, e.g. the console).
    """
    device = build_device(drive, slave_id)
    ready = threading.Event()
    state: dict[str, ModbusTcpServer] = {}

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _serve() -> None:
            server = ModbusTcpServer(device, address=(host, port))
            state["server"] = server
            if not await server.listen():
                raise RuntimeError(f"Could not listen on {host}:{port}")
            ready.set()
            await server.serving

        try:
            loop.run_until_complete(_serve())
        finally:
            loop.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    ready.wait(timeout=5)

    def stop() -> None:
        server = state.get("server")
        if server is None:
            return
        future = asyncio.run_coroutine_threadsafe(server.shutdown(), server.loop)
        future.result(timeout=5)
        thread.join(timeout=5)

    return thread, stop
