# ATV340 Schneider Simulator

A Modbus TCP simulator for the Schneider Electric Altivar ATV340 variable-speed
drive (VFD), for developing and testing PLC/SCADA control logic without
needing physical hardware.

Models the drive's CiA 402 control/status state machine, speed ramping, fault
injection, and a representative set of digital and analog I/O.

## Install

```sh
uv sync
```

## Run

```sh
uv run modbus-simulator
```

This starts a Modbus TCP server on `0.0.0.0:5020` (slave/device id `0`) and
drops into an interactive console.

### CLI options

| Flag | Default | Description |
|---|---|---|
| `--host` | `0.0.0.0` | Address to listen on |
| `--port` | `5020` | TCP port (use `--port 502` to match a real PLC config; may need elevated privileges) |
| `--slave-id` | `0` | Modbus device/slave id |
| `--speed-ramp-hz-per-s` | `10.0` | Simulated accel/decel rate |
| `--initial-speed-ref` | `0.0` | Initial speed reference, Hz |
| `--log-level` | `INFO` | Logging level |
| `--no-console` | off | Run headless (for scripted/CI use); blocks until Ctrl+C |

### Console commands

- `status` — show the current drive state, registers, and I/O
- `set speed_ref <hz>` — set the speed reference
- `set di<n> <0|1>` — force digital input LI*n* (n = 1-6)
- `set ai<n> <value>` — force analog input *n* (n = 1-2)
- `fault <code_or_name>` — inject a fault, e.g. `fault 9` or `fault OCF`
- `reset` — clear the current fault
- `quit` / `exit` — stop the simulator

## Commissioning CLI tools

`modbus-poll` and `modbus-set` are standalone Modbus TCP *clients* — separate
processes from the simulator, talking over the wire like a PLC or a
commissioning laptop would. Point them at this simulator during development,
or at a real ATV340 drive's IP during commissioning; the register map is the
real vendor map either way.

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Modbus server address |
| `--port` | `5020` | Modbus TCP port |
| `--slave-id` | `0` | Modbus device/slave id |
| `--watch` (`modbus-poll` only) | off | Poll continuously until Ctrl+C |
| `--interval` (`modbus-poll` only) | `1.0` | Seconds between reads in `--watch` mode |

Registers can be addressed by friendly name (`speed_ref`, `status_word`,
`cmd_word`, `output_freq`, `fault_word`, `digital_inputs`, `digital_outputs`,
`analog_input_1`, `analog_input_2`, `analog_output_1`), by vendor code
(`lfr`, `eta`, `cmd`, ...; case-insensitive), or by a raw numeric Modbus
address (`8502`, `0x2136`) for anything not in the map.

```sh
# Read one or more registers once
uv run modbus-poll --port 5020 status_word speed_ref

# Watch output frequency ramp in real time (e.g. against the simulator)
uv run modbus-poll --port 5020 output_freq --watch --interval 0.5

# Write a register
uv run modbus-set --port 5020 speed_ref 25.0

# Against real hardware
uv run modbus-poll --host 10.0.0.5 --port 502 status_word
uv run modbus-set --host 10.0.0.5 --port 502 cmd_word 0x000F
```

Connection failures, unknown register names, and Modbus errors are reported
as a single `error: ...` line on stderr with a non-zero exit code.

## Register map

Registers and bit layouts are sourced from Schneider Electric's official
"ATV340 Communication Parameters" spreadsheet (document reference NVE61728,
version 4.6). The spreadsheet itself isn't included in this repository.

| Register | Code | Address | Access | Notes |
|---|---|---|---|---|
| Command word | CMD | 8501 | R/W | CiA 402 control word |
| Status word | ETA | 3201 | R | CiA 402 status word |
| Speed reference | LFR | 8502 | R/W | 0.1 Hz units |
| Output frequency (actual) | RFR | 3202 | R | 0.1 Hz units |
| Last fault code | LFT | 7121 | R | Enumeration |
| Digital inputs (LI1-LI6) | IL1R | 5202 | R | Bitfield |
| Digital outputs (R1, R2, DO1) | OL1R | 5212 | R/W | Bitfield |
| Analog input 1 | AI1R | 5232 | R | |
| Analog input 2 | AI2R | 5233 | R | |
| Analog output 1 | AO1R | 5261 | R/W | |

## Testing

```sh
uv run pytest
```
