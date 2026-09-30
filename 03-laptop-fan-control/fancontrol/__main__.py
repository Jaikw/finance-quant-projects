from __future__ import annotations

import argparse
import sys

from .core import DEFAULT_SAFETY_TEMP_C, RPM_MAX
from .controller import FanController
from .fans import LhmFanBackend, UnavailableFanBackend
from .sensors import LhmSensorSource, SensorUnavailable

NO_CONTROL_REASON = (
    "LibreHardwareMonitor found no controllable fan on this laptop, so temperatures are "
    "shown read-only. Run `python -m fancontrol --probe` to see what the hardware exposes."
)


def build_controller(args: argparse.Namespace) -> FanController:
    if args.simulate:
        from .simulation import SimulatedLaptop

        laptop = SimulatedLaptop()
        return FanController(laptop.source, laptop.fan, args.safety_temp)

    source = LhmSensorSource()
    controls = source.control_sensors()
    fan = LhmFanBackend(controls, args.fan_max_rpm) if controls else UnavailableFanBackend(NO_CONTROL_REASON)
    return FanController(source, fan, args.safety_temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fancontrol", description=__doc__)
    parser.add_argument("--simulate", action="store_true", help="use a simulated laptop (works on any OS)")
    parser.add_argument("--probe", action="store_true", help="write probe_report.txt describing this laptop's sensors/fans and exit")
    parser.add_argument("--safety-temp", type=float, default=DEFAULT_SAFETY_TEMP_C, metavar="C",
                        help="in manual mode, return the fan to Auto if any sensor reaches this (default %(default)s)")
    parser.add_argument("--interval", type=float, default=1.0, metavar="S", help="seconds between readings (default %(default)s)")
    parser.add_argument("--fan-max-rpm", type=int, default=RPM_MAX,
                        help="RPM that 100%% fan duty corresponds to, used to convert the slider to duty (default %(default)s)")
    args = parser.parse_args(argv)

    if args.probe:
        from .probe import run_probe

        run_probe()
        return 0

    try:
        controller = build_controller(args)
    except SensorUnavailable as exc:
        print(exc, file=sys.stderr)
        print("Tip: `python -m fancontrol --simulate` runs the UI without hardware.", file=sys.stderr)
        return 2

    from .app import run

    run(controller, args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
