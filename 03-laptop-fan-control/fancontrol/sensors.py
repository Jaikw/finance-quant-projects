"""Temperature / fan-tachometer readers."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .core import FanReading, Snapshot, TempReading


class SensorUnavailable(RuntimeError):
    """The sensor backend could not be started on this machine."""


class SensorSource(ABC):
    name: str

    @abstractmethod
    def read(self) -> Snapshot: ...

    def close(self) -> None:
        pass


# LibreHardwareMonitor reports a CPU core's *headroom* ("Core #1 Distance to
# TjMax") as a Temperature sensor. It is not a temperature, so drop it.
_NOT_A_TEMPERATURE = ("distance to tjmax",)
_PLAUSIBLE_C = (1.0, 150.0)


class LhmSensorSource(SensorSource):
    """Reads sensors through LibreHardwareMonitorLib (needs Windows + admin rights)."""

    name = "LibreHardwareMonitor"

    def __init__(self) -> None:
        try:
            from HardwareMonitor.Util import OpenComputer, SensorTypeString
        except Exception as exc:  # ImportError off-Windows; pythonnet/.NET errors on it
            raise SensorUnavailable(
                "Could not load LibreHardwareMonitor "
                f"({type(exc).__name__}: {exc}). On Windows run: pip install HardwareMonitor"
            ) from exc
        self._kind = SensorTypeString
        self._computer = OpenComputer(
            cpu=True, gpu=True, motherboard=True, controller=True, storage=True, battery=True
        )

    def walk(self, hardware=None):
        """Yield (hardware, sensor) for the whole tree, sub-hardware included."""
        for hw in self._computer.Hardware if hardware is None else hardware.SubHardware:
            for sensor in hw.Sensors:
                yield hw, sensor
            yield from self.walk(hw)

    def kind_of(self, sensor) -> str:
        return self._kind.get(sensor.SensorType, str(sensor.SensorType))

    def read(self) -> Snapshot:
        self._computer.Update()
        temps: list[TempReading] = []
        fans: list[FanReading] = []
        for hw, sensor in self.walk():
            value = sensor.Value
            if value is None:
                continue
            kind = self.kind_of(sensor)
            if kind == "Temperature":
                lo, hi = _PLAUSIBLE_C
                if lo <= value <= hi and not any(n in sensor.Name.lower() for n in _NOT_A_TEMPERATURE):
                    temps.append(TempReading(sensor.Name, float(value), hw.Name))
            elif kind == "Fan":
                fans.append(FanReading(sensor.Name, float(value), hw.Name))
        return Snapshot(time.time(), tuple(temps), tuple(fans))

    def control_sensors(self) -> list:
        """(hardware, sensor) pairs whose sensor exposes a writable IControl."""
        return [
            (hw, s)
            for hw, s in self.walk()
            if self.kind_of(s) == "Control" and s.Control is not None
        ]

    def report(self) -> str:
        """LibreHardwareMonitor's own full hardware report (what its developers ask for in bug reports)."""
        return self._computer.GetReport()

    def close(self) -> None:
        self._computer.Close()
