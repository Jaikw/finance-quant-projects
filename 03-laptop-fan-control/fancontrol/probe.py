"""`python -m fancontrol --probe`: dump what this laptop exposes, for wiring up fan control.

Whether RPM control is possible at all depends on the laptop's embedded
controller. This writes one text file (sensors, controllable channels, the
LibreHardwareMonitor hardware report, and any Lenovo/fan/thermal WMI classes)
that shows exactly what is available.
"""
from __future__ import annotations

import ctypes
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from .sensors import LhmSensorSource, SensorUnavailable

_POWERSHELL = [
    ("Computer model", "Get-CimInstance Win32_ComputerSystem | Format-List Manufacturer,Model,SystemFamily,SystemSKUNumber"),
    ("BIOS", "Get-CimInstance Win32_BIOS | Format-List Manufacturer,SMBIOSBIOSVersion,ReleaseDate"),
    (
        r"WMI classes in root\WMI matching Lenovo|Fan|Thermal|Cooling",
        r"Get-CimClass -Namespace root\WMI | Where-Object CimClassName -match 'Lenovo|Fan|Thermal|Cooling|GameZone' "
        "| Select-Object -ExpandProperty CimClassName",
    ),
    (
        r"WMI classes in root\CIMV2 matching Lenovo|Fan|Thermal",
        r"Get-CimClass -Namespace root\CIMV2 | Where-Object CimClassName -match 'Lenovo|Fan|Thermal' "
        "| Select-Object -ExpandProperty CimClassName",
    ),
    ("Windows power plan", "powercfg /getactivescheme"),
]


def _powershell(command: str) -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(could not run PowerShell: {exc})"
    return (out.stdout + out.stderr).strip() or "(no output)"


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def build_report() -> str:
    out = [
        f"fancontrol probe - {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Platform: {platform.platform()}",
        f"Running as Administrator: {_is_admin()}",
        "",
    ]
    try:
        source = LhmSensorSource()
    except SensorUnavailable as exc:
        out += [f"LibreHardwareMonitor unavailable: {exc}", ""]
    else:
        try:
            source.read()  # refresh once so every sensor has a value
            out.append("== Sensors (LibreHardwareMonitor) ==")
            for hw, sensor in source.walk():
                kind = source.kind_of(sensor)
                ctl = "  [CONTROLLABLE]" if kind == "Control" and sensor.Control is not None else ""
                out.append(f"{hw.Name} | {kind} | {sensor.Name} = {sensor.Value}{ctl}")
            controls = source.control_sensors()
            out += ["", f"Controllable fan channels found: {len(controls)}", ""]
            out += ["== LibreHardwareMonitor full report ==", source.report(), ""]
        finally:
            source.close()

    for title, command in _POWERSHELL:
        out += [f"== {title} ==", _powershell(command), ""]
    return "\n".join(out)


def run_probe(path: str = "probe_report.txt") -> Path:
    target = Path(path).resolve()
    target.write_text(build_report(), encoding="utf-8")
    print(f"Hardware report written to {target}")
    return target
