"""A fake laptop, so the app can be developed, demoed and tested anywhere.

One shared thermal model backs both the sensor source and the fan backend, so
moving the slider visibly changes the temperature, and the Auto curve behaves
like a normal firmware fan curve.
"""
from __future__ import annotations

import math
import time
from typing import Callable

from .core import RPM_MAX, RPM_MIN, FanReading, Snapshot, TempReading
from .fans import FanBackend
from .sensors import SensorSource

_AMBIENT_C = 24.0
_SPIN_RATE_RPM_S = 1500.0   # how fast the fan can change speed
_THERMAL_TAU_S = 12.0       # thermal mass: how slowly temperature follows


def _auto_curve(temp_c: float) -> float:
    """Firmware-style curve: floor speed under 50 C, ramping to max at 90 C."""
    frac = (temp_c - 50.0) / 40.0
    return RPM_MIN + max(0.0, min(1.0, frac)) * (RPM_MAX - RPM_MIN)


class SimulatedLaptop:
    def __init__(self, clock: Callable[[], float] = time.monotonic, start_temp: float = 38.0) -> None:
        self._clock = clock
        self._last = clock()
        self._t0 = self._last
        self.temp = start_temp
        self.fan_rpm = float(RPM_MIN)
        self.manual_rpm: int | None = None
        self.source = _SimSource(self)
        self.fan = _SimFan(self)

    def _load_watts(self, t: float) -> float:
        # A slow workload wave with a burst on top: ~12 W idle up to ~48 W.
        wave = 0.5 + 0.5 * math.sin(t / 35.0)
        burst = 12.0 if math.sin(t / 9.0) > 0.85 else 0.0
        return 12.0 + 26.0 * wave + burst

    def advance(self) -> None:
        now = self._clock()
        dt, self._last = now - self._last, now
        if dt <= 0:
            return
        target = self.manual_rpm if self.manual_rpm is not None else _auto_curve(self.temp)
        step = _SPIN_RATE_RPM_S * dt
        self.fan_rpm += max(-step, min(step, target - self.fan_rpm))
        # steady-state temp = ambient + watts * thermal resistance (falls as the fan speeds up)
        resistance = 0.4 + 1500.0 / max(self.fan_rpm, 1.0)
        equilibrium = _AMBIENT_C + self._load_watts(now - self._t0) * resistance
        self.temp += (equilibrium - self.temp) * (1.0 - math.exp(-dt / _THERMAL_TAU_S))


class _SimSource(SensorSource):
    name = "Simulated laptop"

    def __init__(self, laptop: SimulatedLaptop) -> None:
        self._laptop = laptop

    def read(self) -> Snapshot:
        lap = self._laptop
        lap.advance()
        group = "Simulated CPU"
        return Snapshot(
            time.time(),
            temps=(
                TempReading("CPU Package", lap.temp, group),
                TempReading("Core Max", lap.temp - 1.5, group),
                TempReading("Core Average", lap.temp - 4.0, group),
                TempReading("Composite", 34.0 + (lap.temp - 30.0) * 0.3, "Simulated NVMe SSD"),
                TempReading("Battery", 29.0 + (lap.temp - 30.0) * 0.1, "Simulated battery"),
            ),
            fans=(FanReading("Fan #1", lap.fan_rpm, "Simulated embedded controller"),),
        )


class _SimFan(FanBackend):
    name = "Simulated fan"
    note = "Drives the simulated thermal model"

    def __init__(self, laptop: SimulatedLaptop) -> None:
        self._laptop = laptop

    def set_rpm(self, rpm: int) -> None:
        self._laptop.manual_rpm = rpm

    def set_auto(self) -> None:
        self._laptop.manual_rpm = None
