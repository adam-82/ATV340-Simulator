"""Interactive console for manually driving the ATV340 simulator's state."""

import cmd

from .drive_state import Drive
from .registers import (
    DigitalInputBits,
    FAULT_CODES,
    FAULT_NAMES,
)


class SimulatorConsole(cmd.Cmd):
    intro = "ATV340 simulator console. Type 'help' for commands.\n"
    prompt = "atv340> "

    def __init__(self, drive: Drive):
        super().__init__()
        self.drive = drive

    def onecmd(self, line: str) -> bool:
        try:
            return super().onecmd(line)
        except ValueError as exc:
            print(f"error: {exc}")
            return False

    def do_status(self, _arg: str) -> None:
        """status - show the current drive state, registers, and I/O."""
        drive = self.drive
        drive.tick_realtime()
        print(f"state:        {drive.state.name}")
        print(f"command_word: 0x{drive.command_word:04X}")
        print(f"status_word:  0x{drive.status_word:04X}")
        print(f"speed_ref:    {drive.speed_ref_hz:.1f} Hz")
        print(f"output_freq:  {drive.output_freq_hz:.1f} Hz")
        fault_name = FAULT_CODES.get(drive.fault_code, "?")
        print(f"fault_code:   {drive.fault_code} ({fault_name})")
        print(f"digital_in:   {drive.digital_inputs:#06b}")
        print(f"digital_out:  {drive.digital_outputs:#06b}")
        print(f"analog_in:    {drive.analog_inputs}")
        print(f"analog_out:   {drive.analog_outputs}")

    def do_set(self, arg: str) -> None:
        """set <register> <value> - force a speed reference or an input signal.

        Examples:
          set speed_ref 25.0     Set the speed reference (Hz)
          set di1 1               Force digital input LI1 on (0/1)
          set di3 0                Force digital input LI3 off
          set ai1 2500              Force analog input 1's raw value
          set ai2 -100               Force analog input 2's raw value
        """
        parts = arg.split()
        if len(parts) != 2:
            print("usage: set <register> <value>")
            return
        name, raw_value = parts[0].lower(), parts[1]

        if name == "speed_ref":
            self.drive.set_speed_reference(float(raw_value))
        elif name.startswith("di") and name[2:].isdigit():
            bit = int(name[2:]) - 1
            try:
                DigitalInputBits(1 << bit)
            except ValueError:
                print(f"unknown digital input: {name}")
                return
            self.drive.set_digital_input(bit, bool(int(raw_value)))
        elif name in ("ai1", "ai2"):
            index = int(name[2:]) - 1
            self.drive.set_analog_input(index, int(raw_value))
        else:
            print(f"unknown register: {name}")

    def do_fault(self, arg: str) -> None:
        """fault <code_or_name> - inject a fault (e.g. 'fault 9' or 'fault OCF')."""
        arg = arg.strip()
        if not arg:
            print("usage: fault <code_or_name>")
            return
        if arg.isdigit():
            code = int(arg)
        else:
            code = FAULT_NAMES.get(arg.upper())
            if code is None:
                print(f"unknown fault name: {arg}")
                return
        self.drive.inject_fault(code)
        print(f"fault injected: {code} ({FAULT_CODES.get(code, '?')})")

    def do_reset(self, _arg: str) -> None:
        """reset - clear the current fault."""
        self.drive.reset_fault()
        print(f"state: {self.drive.state.name}")

    def do_quit(self, _arg: str) -> bool:
        """quit - exit the console and stop the simulator."""
        return True

    def do_exit(self, arg: str) -> bool:
        """exit - exit the console and stop the simulator."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str) -> bool:
        print()
        return self.do_quit(arg)
