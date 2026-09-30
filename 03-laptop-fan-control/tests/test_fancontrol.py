import sys
import time
import types
import unittest
from unittest import mock

from fancontrol.controller import AUTO, MANUAL, FanController, HardwareWorker
from fancontrol.core import RPM_MAX, RPM_MIN, FanReading, Snapshot, TempReading, clamp_rpm
from fancontrol.fans import FanBackend, FanError, LhmFanBackend, UnavailableFanBackend
from fancontrol.sensors import LhmSensorSource, SensorSource
from fancontrol.simulation import SimulatedLaptop


class FakeSource(SensorSource):
    name = "fake"

    def __init__(self, celsius=50.0):
        self.celsius, self.fail, self.closed = celsius, False, False

    def read(self):
        if self.fail:
            raise OSError("driver went away")
        return Snapshot(0.0, (TempReading("CPU Package", self.celsius, "cpu"),))

    def close(self):
        self.closed = True


class FakeFan(FanBackend):
    name = "fake fan"

    def __init__(self):
        self.calls, self.fail_set = [], False

    def set_rpm(self, rpm):
        if self.fail_set:
            raise FanError("EC refused")
        self.calls.append(("rpm", rpm))

    def set_auto(self):
        self.calls.append(("auto",))


class SnapshotTests(unittest.TestCase):
    def test_clamp_keeps_slider_range(self):
        self.assertEqual(clamp_rpm(0), RPM_MIN)
        self.assertEqual(clamp_rpm(99999), RPM_MAX)
        self.assertEqual(clamp_rpm(3250.4), 3250)

    def test_headline_prefers_cpu_package_over_hotter_sensor(self):
        snap = Snapshot(0, (TempReading("Composite", 70, "ssd"), TempReading("CPU Package", 55, "cpu")))
        self.assertEqual(snap.headline.name, "CPU Package")
        self.assertEqual(snap.hottest.name, "Composite")

    def test_headline_falls_back_to_hottest_and_handles_empty(self):
        self.assertEqual(Snapshot(0, (TempReading("GPU", 60), TempReading("SSD", 40))).headline.name, "GPU")
        empty = Snapshot(0)
        self.assertIsNone(empty.headline)
        self.assertIsNone(empty.fan_rpm)

    def test_fan_rpm_is_fastest_fan(self):
        snap = Snapshot(0, fans=(FanReading("a", 2000), FanReading("b", 3100)))
        self.assertEqual(snap.fan_rpm, 3100)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.src, self.fan = FakeSource(), FakeFan()
        self.ctl = FanController(self.src, self.fan, safety_temp=90)

    def test_manual_clamps_and_reports(self):
        self.ctl.set_manual(20000)
        st = self.ctl.poll()
        self.assertEqual((st.mode, st.target_rpm), (MANUAL, RPM_MAX))
        self.assertEqual(self.fan.calls, [("rpm", RPM_MAX)])

    def test_auto_button_restores_auto(self):
        self.ctl.set_manual(3000)
        self.ctl.set_auto()
        self.assertEqual((self.ctl.mode, self.ctl.target_rpm), (AUTO, None))
        self.assertEqual(self.fan.calls[-1], ("auto",))

    def test_safety_limit_reverts_manual_to_auto(self):
        self.ctl.set_manual(1500)
        self.src.celsius = 91
        st = self.ctl.poll()
        self.assertEqual(st.mode, AUTO)
        self.assertIn("safety limit", st.notice)
        self.assertEqual(self.fan.calls[-1], ("auto",))

    def test_safety_uses_hottest_sensor_not_just_headline(self):
        class Src(FakeSource):
            def read(self):
                return Snapshot(0, (TempReading("CPU Package", 50), TempReading("Composite", 95)))

        ctl = FanController(Src(), self.fan, safety_temp=90)
        ctl.set_manual(2000)
        self.assertEqual(ctl.poll().mode, AUTO)

    def test_below_limit_stays_manual(self):
        self.ctl.set_manual(2000)
        self.src.celsius = 89.9
        self.assertEqual(self.ctl.poll().mode, MANUAL)

    def test_no_safety_action_in_auto_mode(self):
        self.src.celsius = 99
        self.ctl.poll()
        self.assertEqual(self.fan.calls, [])

    def test_losing_sensors_in_manual_returns_to_auto_after_three_failures(self):
        self.ctl.set_manual(2000)
        self.src.fail = True
        self.assertEqual(self.ctl.poll().mode, MANUAL)
        self.assertEqual(self.ctl.poll().mode, MANUAL)
        st = self.ctl.poll()
        self.assertEqual(st.mode, AUTO)
        self.assertIn("Sensor read failed", st.notice)

    def test_sensor_recovery_clears_read_failed_notice(self):
        self.src.fail = True
        self.assertIn("Sensor read failed", self.ctl.poll().notice)
        self.src.fail = False
        self.assertEqual(self.ctl.poll().notice, "")

    def test_backend_error_leaves_us_in_auto_with_notice(self):
        self.fan.fail_set = True
        self.ctl.set_manual(2000)
        self.assertEqual(self.ctl.mode, AUTO)
        self.assertIn("EC refused", self.ctl.notice)

    def test_unavailable_backend_refuses_manual(self):
        ctl = FanController(self.src, UnavailableFanBackend("no EC driver"), 90)
        ctl.set_manual(3000)
        st = ctl.state()
        self.assertEqual(st.mode, AUTO)
        self.assertFalse(st.can_control)
        self.assertIn("no EC driver", st.notice)

    def test_shutdown_restores_auto_only_if_fan_was_touched(self):
        self.ctl.shutdown()
        self.assertEqual(self.fan.calls, [])
        self.assertTrue(self.src.closed)
        self.ctl.set_manual(2500)
        self.ctl.shutdown()
        self.assertEqual(self.fan.calls[-1], ("auto",))


class WorkerTests(unittest.TestCase):
    def test_worker_applies_commands_and_restores_auto_on_stop(self):
        fan = FakeFan()
        worker = HardwareWorker(FanController(FakeSource(), fan), interval=0.02)
        worker.start()
        worker.set_manual(4000)
        deadline = time.time() + 2
        seen = None
        while time.time() < deadline and seen != (MANUAL, 4000):
            try:
                st = worker.states.get(timeout=0.1)
                seen = (st.mode, st.target_rpm)
            except Exception:
                pass
        self.assertEqual(seen, (MANUAL, 4000))
        worker.stop()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(fan.calls[-1], ("auto",))


class SimulationTests(unittest.TestCase):
    def make(self):
        self.now = 0.0
        return SimulatedLaptop(clock=lambda: self.now)

    def run_for(self, lap, seconds):
        for _ in range(int(seconds)):
            self.now += 1.0
            lap.source.read()

    def test_more_fan_means_cooler(self):
        slow, fast = self.make(), self.make()
        slow.fan.set_rpm(RPM_MIN)
        self.run_for(slow, 120)
        low_temp = slow.temp

        self.now = 0.0
        fast = SimulatedLaptop(clock=lambda: self.now)
        fast.fan.set_rpm(RPM_MAX)
        self.run_for(fast, 120)
        self.assertLess(fast.temp, low_temp - 10)

    def test_auto_curve_idles_when_cool_and_ramps_when_hot(self):
        cool = self.make()
        cool.temp = 40.0
        cool.fan.set_auto()
        self.run_for(cool, 1)
        self.assertEqual(cool.fan_rpm, RPM_MIN)

        self.now = 0.0
        hot = SimulatedLaptop(clock=lambda: self.now)
        hot.temp = 85.0
        hot.fan.set_auto()
        self.run_for(hot, 3)
        self.assertGreater(hot.fan_rpm, 4000)

    def test_snapshot_shape(self):
        snap = self.make().source.read()
        self.assertEqual(snap.headline.name, "CPU Package")
        self.assertIsNotNone(snap.fan_rpm)



# --- LibreHardwareMonitor adapters, exercised against stand-in .NET objects ------------------

class FakeControl:
    MinSoftwareValue, MaxSoftwareValue = 0.0, 100.0

    def __init__(self, fail_default=False):
        self.software, self.defaulted, self.fail_default = None, 0, fail_default

    def SetSoftware(self, value):
        self.software = value

    def SetDefault(self):
        if self.fail_default:
            raise OSError("EC busy")
        self.defaulted += 1


class FakeSensor:
    def __init__(self, name, kind, value, control=None):
        self.Name, self.SensorType, self.Value, self.Control = name, kind, value, control


class FakeHardware:
    def __init__(self, name, sensors=(), sub=()):
        self.Name, self.Sensors, self.SubHardware = name, list(sensors), list(sub)


class FakeComputer:
    def __init__(self, hardware):
        self.Hardware, self.closed = hardware, False

    def Update(self):
        pass

    def Close(self):
        self.closed = True


def lhm_source(hardware):
    util = types.ModuleType("HardwareMonitor.Util")
    util.SensorTypeString = {4: "Temperature", 7: "Fan", 9: "Control"}
    util.OpenComputer = lambda **_kw: FakeComputer(hardware)
    pkg = types.ModuleType("HardwareMonitor")
    pkg.Util = util
    with mock.patch.dict(sys.modules, {"HardwareMonitor": pkg, "HardwareMonitor.Util": util}):
        return LhmSensorSource()


class LhmAdapterTests(unittest.TestCase):
    def hardware(self):
        self.ctl = FakeControl()
        cpu = FakeHardware("Intel CPU", [
            FakeSensor("CPU Package", 4, 61.0),
            FakeSensor("Core #1 Distance to TjMax", 4, 39.0),   # headroom, not a temperature
            FakeSensor("Core Max", 4, 63.0),
            FakeSensor("Broken", 4, None),
            FakeSensor("Zero", 4, 0.0),
        ])
        board = FakeHardware("Board", [FakeSensor("Fan #1", 7, 2400.0), FakeSensor("Fan Control", 9, 30.0, self.ctl)],
                             sub=[FakeHardware("EC", [FakeSensor("VRM", 4, 55.0)])])
        return [cpu, board]

    def test_reads_real_temps_and_fans_only(self):
        snap = lhm_source(self.hardware()).read()
        self.assertEqual({t.name for t in snap.temps}, {"CPU Package", "Core Max", "VRM"})
        self.assertEqual(snap.fan_rpm, 2400.0)
        self.assertEqual(snap.headline.name, "CPU Package")

    def test_finds_controls_including_sub_hardware_and_drives_them(self):
        src = lhm_source(self.hardware())
        controls = src.control_sensors()
        self.assertEqual(len(controls), 1)
        fan = LhmFanBackend(controls, max_rpm=6000)
        fan.set_rpm(3000)
        self.assertEqual(self.ctl.software, 50.0)      # 3000 / 6000 RPM -> 50 % duty
        fan.set_rpm(9000)
        self.assertEqual(self.ctl.software, 100.0)     # never above 100 %
        fan.set_auto()
        self.assertEqual(self.ctl.defaulted, 1)

    def test_set_auto_tries_every_channel_even_if_one_fails(self):
        bad, good = FakeControl(fail_default=True), FakeControl()
        pairs = [(FakeHardware("a"), FakeSensor("x", 9, 0, bad)), (FakeHardware("b"), FakeSensor("y", 9, 0, good))]
        with self.assertRaises(FanError):
            LhmFanBackend(pairs).set_auto()
        self.assertEqual(good.defaulted, 1)

    def test_missing_library_gives_a_friendly_error(self):
        from fancontrol.sensors import SensorUnavailable

        with mock.patch.dict(sys.modules, {"HardwareMonitor": None, "HardwareMonitor.Util": None}):
            with self.assertRaises(SensorUnavailable):
                LhmSensorSource()


if __name__ == "__main__":
    unittest.main()
