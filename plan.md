# ATV340 Modbus TCP Simulator — Implementation Plan

## Context

`/home/adam/modbus_simulator` is a bare `uv`-scaffolded Python project. The README states the intent — "ATV340 Schneider Simulator" — but no simulator logic exists yet: `src/modbus_simulator/__init__.py` is just a placeholder `main()` that prints a greeting, there are no dependencies, no tests, no CI.

The goal is to build a **Modbus TCP simulator that emulates a Schneider Electric Altivar ATV340 variable-speed drive (VFD)**, so the user can develop and test PLC/SCADA control logic against something that behaves like the real drive without needing physical hardware. Real register addresses have been extracted from Schneider's official ATV340 communication parameters spreadsheet (doc ref NVE61728, v4.6), so `registers.py` will be built with verified values from the start rather than placeholders. The source spreadsheet itself stays out of git (copyrighted vendor document); only the extracted constants (with a provenance comment) are checked in.

Confirmed decisions:
- **Transport:** Modbus TCP only (no RTU/serial) for v1.
- **Default port:** `5020` (avoids needing root/capabilities for local dev); `--port 502` documented for matching real PLC configs.
- **Interface:** CLI to launch/configure the simulator, plus an in-process interactive console (stdlib `cmd` loop) to manually set registers, inject faults, and inspect state while the server runs.
- **Register addresses:** verified real values (see tables below), sourced from doc NVE61728 v4.6.
- **Scope:** single drive/slave, no persistence, no config files, no multi-drive, no scripted fault sequences.
- **I/O:** simulator also models digital and analog inputs/outputs, not just the drive control/status words.

### Verified ATV340 register map (source: NVE61728 v4.6)

| Register | Code | Modbus address (decimal) | Access | Type | Notes |
|---|---|---|---|---|---|
| Command word | CMD | 8501 (0x2135) | R/W | WORD (bitfield) | CiA 402 control word |
| Status word | ETA | 3201 (0x0C81) | R | WORD (bitfield) | CiA 402 status word |
| Speed/reference frequency setpoint | LFR | 8502 (0x2136) | R/W | INT16, 0.1 Hz units | Range -5990...5990 |
| Motor (output) frequency, actual | RFR | 3202 (0x0C82) | R | INT16, 0.1 Hz units | Range ±3276.7 Hz |
| Last fault code | LFT | 7121 (0x1BD1) | R | WORD (enumeration) | See fault code table below |

**CMD (control word) bits** — standard CiA 402: bit0 switch-on, bit1 disable/enable voltage, bit2 quick stop, bit3 enable operation, bits4–6 reserved (0), bit7 fault reset (0→1 transition), bit8 halt, bits9–10 reserved, bits11–15 assignable.

**ETA (status word) bits** — standard CiA 402: bit0 ready to switch on, bit1 switched on, bit2 operation enabled, bit3 fault, bit4 voltage enabled, bit5 quick stop (0=active), bit6 switched-on-disabled, bit7 warning, bit8 reserved, bit9 remote (fieldbus command/reference active), bit10 target reference reached, bit11 internal limit active.

**LFT fault codes (representative subset for v1)**: 0=NOF (no error), 9=OCF (overcurrent), 16=OHF (device overheat), 17=OLF (motor overload), 18=OBF (DC bus overvoltage), 19=OSF (supply mains overvoltage), 22=USF (supply mains undervoltage), 23=SCF1 (motor short circuit), 24=SOF (motor overspeed). Full list has ~80 codes; v1 only needs a representative handful for `inject_fault()`/`FAULT_CODES`, more can be added later straight from the spreadsheet without further vendor lookups.

### Digital / analog I/O registers (also from NVE61728 v4.6)

| Register | Code | Modbus address | Access | Type | Notes |
|---|---|---|---|---|---|
| Digital inputs (bitfield) | IL1R | 5202 (0x1452) | R | WORD (bitfield) | "Logic inputs real image" |
| Digital outputs (bitfield) | OL1R | 5212 (0x145C) | R/W | WORD (bitfield) | "Logic outputs real image" — network can force outputs |
| Analog input 1 | AI1R | 5232 (0x1470) | R | INT16 | "Analog input 1 standardized value", range ±32767 |
| Analog input 2 | AI2R | 5233 (0x1471) | R | INT16 | same pattern |
| Analog output 1 | AO1R | 5261 (0x148D) | R/W | INT16 | "Analog output 1 standardized value" — network can force output |

**IL1R (digital inputs) bits**: bit0 LI1, bit1 LI2, bit2 LI3, bit3 LI4, bit4 LI5, bit5 LI6, bit6 LI7, bit7 LI8, bits8–9 reserved, bit10 LI11, bit11 LI12, bit12 LI13, bit13 LI14, bit14 LI15, bit15 LI16. v1 only needs LI1–LI6 (the physically-present inputs on a base ATV340); the rest read as 0.

**OL1R (digital outputs) bits**: bit0 R1 (relay), bit1 R2, bits2–5 R3–R6 (reserved on base unit), bits6–7 reserved, bit8 DO1, bit9 DO2, bits10–11 reserved, bit12 DO11, bit13 DO12, bits14–15 reserved. v1 only needs R1, R2, DO1 (the physically-present outputs on a base ATV340).

v1 keeps this to one digital-input word, one digital-output word, and 2 analog inputs + 1 analog output — matching the register set above — rather than the full AI1–AI5/AO1–AO2 spread; more can be added later the same way since they're already in the source spreadsheet.

## Approach

### Dependencies
Add `pymodbus>=3.15,<4.0` as a runtime dependency (`uv add pymodbus`) and `pytest>=8` as a dev dependency (`uv add --dev pytest`). pymodbus's own client (`pymodbus.client.ModbusTcpClient`) is used for integration tests — no separate client library needed.

### Module breakdown (all under `src/modbus_simulator/`)

**`registers.py`** — single source of truth for the ATV340 register map, populated with the verified addresses above. Defines a `Register` NamedTuple (address, name, description), constants `CMD_WORD=8501`, `STATUS_WORD=3201`, `SPEED_REF=8502`, `OUTPUT_FREQ=3202`, `FAULT_WORD=7121`, `DIGITAL_INPUTS=5202`, `DIGITAL_OUTPUTS=5212`, `ANALOG_INPUT_1=5232`, `ANALOG_INPUT_2=5233`, `ANALOG_OUTPUT_1=5261`, `CmdBits`/`StatusBits` `IntFlag` enums matching the real CiA 402 bit layout above, `DigitalInputBits`/`DigitalOutputBits` `IntFlag` enums for LI1–LI6/R1/R2/DO1, and a `FAULT_CODES` dict seeded from the LFT enumeration (NOF, OCF, OHF, OLF, OBF, OSF, USF, SCF1, SOF — extendable later from the same spreadsheet). A top-of-file comment cites the source doc (NVE61728 v4.6) for provenance.

**`drive_state.py`** — pure logic, zero pymodbus imports, the highest-value unit-test target. `DriveState` enum modeling the CiA 402 state diagram (Not Ready → Switch On Disabled → Ready to Switch On → Switched On → Operation Enabled → Fault, etc.). `Drive` class holding state + command/status words + speed ref + output frequency + fault code + I/O state (`digital_inputs: int` bitfield, `digital_outputs: int` bitfield, `analog_inputs: list[int]`, `analog_outputs: list[int]`), with methods: `apply_command_word()` (decodes bits, runs state transitions, recomputes status word), `set_speed_reference()`, `tick(dt)` (ramps output frequency toward setpoint at a configurable rate — modeling real VFD accel/decel behavior), `inject_fault()`, `reset_fault()` (only clears if command word's fault-reset bit is set), `set_digital_input(bit, value)`/`set_analog_input(index, value)` (simulate real-world signals arriving at the drive — settable via the console, read-only over Modbus), `set_digital_output(word)`/`set_analog_output(index, value)` (writable over Modbus too, since a real PLC can force these — mirrors the register table's R/W access).

**`server.py`** — wires pymodbus's async TCP server to the `Drive` object. A `DriveDataBlock(ModbusSequentialDataBlock)` subclass overrides `setValues` so writes to `CMD_WORD`/`SPEED_REF`/`DIGITAL_OUTPUTS`/`ANALOG_OUTPUT_1` addresses route through `Drive` methods instead of just storing raw values. `build_context(drive, slave_id)` constructs the `ModbusServerContext`. `run_server(...)` runs `StartAsyncTcpServer` plus a periodic task calling `drive.tick()` and pushing computed values (status word, output freq, fault word, digital inputs, analog inputs) into the datastore. `start_server_thread(...)` wraps this in a background thread with its own event loop and returns a `stop()` callable.

**`console.py`** — `SimulatorConsole(cmd.Cmd)`, a thin stdlib REPL talking directly to the shared `Drive` object in-process (no second Modbus client needed). Commands: `status` (pretty-print state/words/fault/I-O), `set <register> <value>` (covers speed ref and forcing a digital/analog input, e.g. `set di1 1`, `set ai1 2500`), `fault <code_or_name>`, `reset`, `quit`/`exit` (also stops the server thread). No business logic here — just argument parsing delegating to `Drive`/`registers`.

**`cli.py`** — stdlib `argparse` (no click/typer — surface area is small). Flags: `--host` (default `0.0.0.0`), `--port` (default `5020`), `--slave-id` (default `0`), `--speed-ramp-hz-per-s`, `--initial-speed-ref`, `--log-level`, `--no-console` (headless mode for scripted/CI use — blocks on Ctrl+C instead of running the REPL, since the interactive console can't be part of automated tests). `main(argv=None)` parses args, builds `Drive`, starts the server thread, then runs the console or blocks.

**`__init__.py`** — reduced to `from .cli import main` / `__all__ = ["main"]`, keeping the existing `pyproject.toml` entry point (`modbus-simulator = "modbus_simulator:main"`) working unchanged.

### Tests (`tests/`, new directory)
- `tests/test_drive_state.py` — pure unit tests, no networking: default power-up state, the standard CiA 402 bring-up command sequence reaching `OPERATION_ENABLED`, speed ramping across multiple `tick()` calls, fault injection forcing `FAULT` + zeroing output, fault-reset gated on the reset bit, digital input bit set/read, digital output write reflected in `digital_outputs`, analog input/output set/read round-trips.
- `tests/test_server_integration.py` — spins up the real server on a fixed local test port (e.g. `127.0.0.1:15020`), uses `pymodbus.client.ModbusTcpClient` to read the status word, write command-word bits to reach operation-enabled, write a speed reference, poll output frequency across ticks and assert it approaches the setpoint, exercise fault/reset via register writes, and exercise the I/O registers (read digital-input word after console sets a bit, write the digital-output/analog-output registers over Modbus and confirm `Drive` reflects the change). Shared pytest fixture handles server thread setup/teardown.

### README update
Add usage instructions (install, run, CLI flags) and a note citing the register map's source (NVE61728 v4.6) for provenance.

## Explicitly out of scope for v1
Modbus RTU/serial, config files, multi-drive/multi-slave support, state persistence across restarts, scripted/timed fault-injection sequences, a second control channel (e.g. HTTP API) beyond the in-process console, and full ATV340 parameter/menu register coverage beyond command/status/speed/frequency/fault/the I/O registers listed above (i.e. only LI1–LI6, R1/R2/DO1, AI1/AI2, AO1 — not the full LI1–LI16/R1–R6/DO1-DO12/AI1–AI5/AO1–AO2 spread).

## Order of work
1. `registers.py` with the verified constants above.
2. `drive_state.py` + `tests/test_drive_state.py`.
3. Add `pymodbus` dependency; write `server.py`.
4. `tests/test_server_integration.py`.
5. `cli.py`; update `__init__.py` entry point.
6. `console.py`; wire into `cli.main`.
7. Update `README.md`.

## Verification
- `uv run pytest` — unit tests for `drive_state.py` pass with no network dependency; integration tests confirm the TCP server responds correctly to a real Modbus client (register reads/writes, state transitions, fault behavior).
- Manual check: `uv run modbus-simulator` starts the server + console; from another terminal, connect with `pymodbus.console`/`mbpoll`/a PLC test tool against `127.0.0.1:5020`, bring the drive through the CiA 402 bring-up sequence, set a speed reference, and confirm output frequency ramps and the console's `status` command reflects the same state. Also confirm: setting a digital/analog input via the console shows up on a Modbus read of `DIGITAL_INPUTS`/`ANALOG_INPUT_1`, and writing `DIGITAL_OUTPUTS`/`ANALOG_OUTPUT_1` from the Modbus client is reflected in the console's `status` output.
