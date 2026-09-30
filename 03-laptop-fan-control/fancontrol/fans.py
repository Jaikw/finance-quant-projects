"""Fan-speed backends.

A backend only has to do two things: pin the fan to an RPM, and give control
back to the machine's own thermal curve. Which backend can work depends on the
laptop's embedded controller, so the app picks one at start-up and reports
honestly when none is available.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .core import RPM_MAX


class FanError(RuntimeError):
    pass


class FanBackend(ABC):
    name: str
    available: bool = True
    note: str = ""  # what it drives, or why it is unavailable

    @abstractmethod
    def set_rpm(self, rpm: int) -> None: ...

    @abstractmethod
    def set_auto(self) -> None:
        """Hand the fan back to the system's own curve."""


class UnavailableFanBackend(FanBackend):
    name = "none"
    available = False

    def __init__(self, reason: str) -> None:
        self.note = reason

    def set_rpm(self, rpm: int) -> None:
        raise FanError(self.note)

    def set_auto(self) -> None:
        pass


class LhmFanBackend(FanBackend):
    """Drives LibreHardwareMonitor 'Control' sensors (fan duty %, software override).

    LibreHardwareMonitor only exposes these where it has a driver for the
    machine's fan controller (Super I/O chips, some embedded controllers).
    Duty cycle is not RPM, so we assume 100 % duty == ``max_rpm``.
    """

    name = "LibreHardwareMonitor control"

    def __init__(self, controls: list, max_rpm: int = RPM_MAX) -> None:
        self._controls = controls  # [(hardware, sensor)]
        self._max_rpm = max_rpm
        self.note = "Drives " + ", ".join(f"{hw.Name} / {s.Name}" for hw, s in controls)

    def set_rpm(self, rpm: int) -> None:
        percent = max(0.0, min(100.0, rpm / self._max_rpm * 100.0))
        for _, sensor in self._controls:
            ctl = sensor.Control
            ctl.SetSoftware(max(ctl.MinSoftwareValue, min(ctl.MaxSoftwareValue, percent)))

    def set_auto(self) -> None:
        errors = []
        for hw, sensor in self._controls:  # try every channel even if one fails
            try:
                sensor.Control.SetDefault()
            except Exception as exc:
                errors.append(f"{hw.Name} / {sensor.Name}: {exc}")
        if errors:
            raise FanError("; ".join(errors))
