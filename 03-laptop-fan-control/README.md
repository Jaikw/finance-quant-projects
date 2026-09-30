# Laptop Thermals & Fan Control

A small Windows desktop app (Python + Tkinter) that shows your laptop's live temperatures and lets you set the fan speed with a slider (1,500 – 6,000 RPM), with one button to hand the fan back to the system's normal automatic curve.

- **Live temps** – big CPU readout, a rolling history graph, and every temperature sensor the hardware reports.
- **Fan slider** – 1,500 – 6,000 RPM in 100 RPM steps; applies when you let go of the slider.
- **Auto button** – returns the fan to the laptop's own thermal curve.
- **Safety net** – in manual mode the fan is automatically returned to Auto if any sensor reaches 90 °C (`--safety-temp`), if sensor readings are lost, or when you close the app.

## Read this first: fan control depends on your laptop

Temperatures come from [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) and work on most machines. **Fan control is different**: on most laptops the fan is run by the embedded controller (EC), and there is no standard Windows API to override it. The slider only works if LibreHardwareMonitor exposes a writable fan channel for your model.

- If it does, the slider is live and drives it (duty % is derived from RPM assuming 100 % duty = `--fan-max-rpm`, default 6,000).
- If it doesn't (common on Lenovo Yoga-class 2-in-1s, where cooling is managed by Lenovo's firmware/Vantage), the app runs **read-only**: temps and fan RPM are shown, the slider is disabled, and a banner says why.

This was built and tested in a Linux container against a simulated laptop, **not on real hardware**. Run the probe on your laptop to find out what's possible:

```
python -m fancontrol --probe
```

It writes `probe_report.txt` (sensors, controllable channels, LibreHardwareMonitor's hardware report, and any Lenovo/fan/thermal WMI classes). That file shows exactly what a real fan backend for your machine would have to talk to — see `fancontrol/fans.py` (a backend is two methods: `set_rpm`, `set_auto`).

## Run it (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/).
2. Install the PawnIO driver LibreHardwareMonitor uses for CPU/EC access: `winget install PawnIO`
3. From this folder: `pip install -r requirements.txt`
4. **Open the terminal as Administrator**, then: `python -m fancontrol`

No hardware handy (or just want to see the UI)? `python -m fancontrol --simulate` runs against a simulated laptop on any OS with Tkinter; moving the slider visibly changes the simulated temperature.

Options: `--safety-temp C`, `--interval SECONDS`, `--fan-max-rpm RPM`, `--simulate`, `--probe`.

If the app is ever force-killed while in manual mode, restart it and press **Auto** (or reboot) to be sure the fan is back under system control.

## Tests

```
python -m unittest discover -s tests -t .
```

Covers RPM clamping, headline-sensor choice, the 90 °C revert, sensor-loss revert, restoring Auto on shutdown, and the simulated thermal model.

## Layout

| File | Role |
|---|---|
| `fancontrol/app.py` | Tkinter UI |
| `fancontrol/controller.py` | Safety rules + the single worker thread that owns all hardware access |
| `fancontrol/sensors.py` | LibreHardwareMonitor sensor reader |
| `fancontrol/fans.py` | Fan backends (LibreHardwareMonitor control channels, "unavailable") |
| `fancontrol/simulation.py` | Simulated laptop for demos/tests |
| `fancontrol/probe.py` | `--probe` hardware report |
