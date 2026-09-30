"""Shared constants and plain data types."""
from __future__ import annotations

from dataclasses import dataclass

RPM_MIN = 1500
RPM_MAX = 6000
RPM_STEP = 100

# In manual mode the fan is handed back to the system's own curve if any
# sensor reaches this temperature.
DEFAULT_SAFETY_TEMP_C = 90.0

# Sensor names preferred for the big headline number, best match first.
_HEADLINE_NAMES = ("cpu package", "core max", "cpu total", "core average")


def clamp_rpm(rpm: float) -> int:
    return int(round(max(RPM_MIN, min(RPM_MAX, rpm))))


@dataclass(frozen=True)
class TempReading:
    name: str
    celsius: float
    group: str = ""  # the hardware it belongs to, e.g. "Intel Core Ultra 7 258V"


@dataclass(frozen=True)
class FanReading:
    name: str
    rpm: float
    group: str = ""


@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    temps: tuple[TempReading, ...] = ()
    fans: tuple[FanReading, ...] = ()

    @property
    def hottest(self) -> TempReading | None:
        return max(self.temps, key=lambda t: t.celsius, default=None)

    @property
    def headline(self) -> TempReading | None:
        """The reading shown large: the CPU package temp if we have it, else the hottest."""
        for wanted in _HEADLINE_NAMES:
            for t in self.temps:
                if wanted in t.name.lower():
                    return t
        return self.hottest

    @property
    def fan_rpm(self) -> float | None:
        """Fastest fan we can read, or None if the hardware exposes no tachometer."""
        return max((f.rpm for f in self.fans), default=None)
