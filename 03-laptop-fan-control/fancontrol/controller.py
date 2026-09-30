"""Ties a sensor source and a fan backend together, and owns the safety rules.

Everything that touches hardware runs on one worker thread (LibreHardwareMonitor
objects are not thread-safe); the UI only sends commands and reads states.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from .core import DEFAULT_SAFETY_TEMP_C, Snapshot, clamp_rpm
from .fans import FanBackend
from .sensors import SensorSource

AUTO, MANUAL = "auto", "manual"
_MAX_READ_FAILURES = 3


@dataclass(frozen=True)
class State:
    snapshot: Snapshot | None
    mode: str
    target_rpm: int | None
    can_control: bool
    control_note: str
    notice: str = ""  # last safety event / error; cleared by the next user action


class FanController:
    def __init__(self, source: SensorSource, fan: FanBackend, safety_temp: float = DEFAULT_SAFETY_TEMP_C):
        self.source = source
        self.fan = fan
        self.safety_temp = safety_temp
        self.mode = AUTO
        self.target_rpm: int | None = None
        self.notice = ""
        self._snapshot: Snapshot | None = None
        self._read_failures = 0
        self._touched_fan = False

    # -- user actions ---------------------------------------------------------
    def set_manual(self, rpm: float) -> None:
        self.notice = ""
        if not self.fan.available:
            self.notice = f"Fan control unavailable: {self.fan.note}"
            return
        rpm = clamp_rpm(rpm)
        try:
            self._touched_fan = True
            self.fan.set_rpm(rpm)
        except Exception as exc:
            self.notice = f"Could not set fan speed: {exc}"
            self._revert_to_auto()
            return
        self.mode, self.target_rpm = MANUAL, rpm

    def set_auto(self) -> None:
        self.notice = ""
        self._revert_to_auto()

    def shutdown(self) -> None:
        """Always leave the fan under the system's control."""
        if self._touched_fan:
            self._revert_to_auto()
        self.source.close()

    # -- polling + safety -------------------------------------------------------
    def poll(self) -> State:
        try:
            self._snapshot = self.source.read()
            self._read_failures = 0
            if self.notice.startswith("Sensor read failed"):
                self.notice = ""  # the sensors recovered
        except Exception as exc:
            self._read_failures += 1
            self._snapshot = None
            self.notice = f"Sensor read failed: {exc}"
            if self.mode == MANUAL and self._read_failures >= _MAX_READ_FAILURES:
                self.notice += " - can't see temperatures, so the fan was returned to Auto."
                self._revert_to_auto()
        else:
            hot = self._snapshot.hottest
            if self.mode == MANUAL and hot is not None and hot.celsius >= self.safety_temp:
                self.notice = (
                    f"{hot.name} reached {hot.celsius:.0f} °C (safety limit {self.safety_temp:.0f} °C) "
                    "- fan returned to Auto."
                )
                self._revert_to_auto()
        return self.state()

    def state(self) -> State:
        return State(
            self._snapshot, self.mode, self.target_rpm,
            self.fan.available, self.fan.note, self.notice,
        )

    def _revert_to_auto(self) -> None:
        try:
            self.fan.set_auto()
        except Exception as exc:
            self.notice = (self.notice + " " if self.notice else "") + f"Could not restore Auto: {exc}"
        self.mode, self.target_rpm = AUTO, None


class HardwareWorker(threading.Thread):
    """Polls the controller on a fixed interval and applies UI commands in between."""

    def __init__(self, controller: FanController, interval: float = 1.0):
        super().__init__(name="hardware", daemon=True)
        self.controller = controller
        self.interval = interval
        self.states: queue.Queue[State] = queue.Queue()
        self._commands: queue.Queue[tuple[str, float | None]] = queue.Queue()

    def set_manual(self, rpm: float) -> None:
        self._commands.put(("manual", rpm))

    def set_auto(self) -> None:
        self._commands.put(("auto", None))

    def stop(self) -> None:
        self._commands.put(("stop", None))

    def run(self) -> None:
        next_poll = 0.0
        try:
            while True:
                try:
                    cmd, arg = self._commands.get(timeout=max(0.0, next_poll - time.monotonic()))
                except queue.Empty:
                    cmd, arg = None, None
                if cmd == "stop":
                    return
                if cmd == "manual":
                    self.controller.set_manual(arg)
                    self.states.put(self.controller.state())
                elif cmd == "auto":
                    self.controller.set_auto()
                    self.states.put(self.controller.state())
                if time.monotonic() >= next_poll:
                    self.states.put(self.controller.poll())
                    next_poll = time.monotonic() + self.interval
        finally:
            self.controller.shutdown()
