# SPDX-License-Identifier: GPL-2.0-or-later
import asyncio
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import fakesys  # noqa: E402
from mangmi import fan, hwd, irq, leds, perf, power, protocol, state, sysfs  # noqa: E402


class FakeRootCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        fakesys.build(self.root)
        os.environ["MANGMI_ROOT"] = self.root
        sysfs.forget()

    def tearDown(self):
        os.environ.pop("MANGMI_ROOT", None)
        sysfs.forget()
        self.tmp.cleanup()

    def r(self, rel):
        return fakesys.read(self.root, rel)


class TestLeds(FakeRootCase):
    def test_discovery_order(self):
        rings = leds.LedRings.discover()
        self.assertEqual(len(rings.leds), 18)
        self.assertEqual([d.name for d in rings.leds[:2]], ["rgb:l1", "rgb:l2"])
        self.assertEqual(rings.leds[9].name, "rgb:r1")
        self.assertEqual(rings.ring_size("l"), 9)

    def test_static_two_colors(self):
        rings = leds.LedRings.discover()
        cfg = {"mode": "static", "color": "ff0000", "color2": "0000ff", "speed": 40}
        rings.show(leds.frame(rings, cfg, 0.0, leds.Context()))
        self.assertEqual(self.r("sys/class/leds/rgb:l5/multi_intensity"), "255 0 0")
        self.assertEqual(self.r("sys/class/leds/rgb:r5/multi_intensity"), "0 0 255")

    def test_brightness_percent(self):
        rings = leds.LedRings.discover()
        rings.set_brightness(50)
        self.assertEqual(self.r("sys/class/leds/rgb:r9/brightness"), "128")

    def test_wave_is_a_gradient(self):
        rings = leds.LedRings.discover()
        cfg = {"mode": "wave", "color": "ffffff", "color2": "", "speed": 50}
        colors = leds.frame(rings, cfg, 1.0, leds.Context())
        self.assertEqual(len(set(colors[:9])), 9)

    def test_battery_colors(self):
        self.assertEqual(leds.battery_color(100), (0, 255, 0))
        self.assertEqual(leds.battery_color(1), (255, 0, 0))
        self.assertTrue(leds.is_animated("battery", leds.Context(battery=50, charging=True)))
        self.assertFalse(leds.is_animated("battery", leds.Context(battery=50)))
        self.assertTrue(leds.is_animated("battery", leds.Context(battery=5)))

    def test_thermal_colors(self):
        self.assertEqual(leds.thermal_color(90), (255, 0, 0))
        r, g, b = leds.thermal_color(30)
        self.assertGreater(b, r)


class TestFan(FakeRootCase):
    def test_finds_only_active_fan_trips(self):
        trips = fan.fan_trips()
        self.assertEqual(len(trips), 5)
        self.assertTrue(all(t == 1 for _, t in trips))

    def test_modes(self):
        z0 = "sys/class/thermal/thermal_zone0/trip_point_1_temp"
        zb = "sys/class/thermal/thermal_zone4/trip_point_1_temp"
        self.assertEqual(fan.apply("quiet"), 5)
        self.assertEqual(self.r(z0), "80000")
        self.assertEqual(self.r(zb), "50000")
        fan.apply("cool")  # relative to the *original* values, not the quiet ones
        self.assertEqual(self.r(z0), "55000")
        self.assertEqual(self.r(zb), "45000")
        fan.apply("max")
        self.assertEqual(self.r(z0), "30000")
        fan.apply("auto")
        self.assertEqual(self.r(z0), "70000")
        self.assertEqual(self.r(zb), "40000")
        self.assertEqual(self.r("sys/class/thermal/thermal_zone0/trip_point_0_temp"), "95000")

    def test_running(self):
        self.assertFalse(fan.is_running())


class TestPerf(FakeRootCase):
    pol0 = "sys/devices/system/cpu/cpufreq/policy0"
    pol4 = "sys/devices/system/cpu/cpufreq/policy4"
    gpu = "sys/class/devfreq/5900000.gpu"

    def test_domains(self):
        kinds = sorted(d.kind for d in perf.cpu_domains())
        self.assertEqual(kinds, ["big", "little"])
        self.assertEqual(perf.gpu_domain().hi, 1050000000)

    def test_powersave(self):
        perf.apply("powersave")
        self.assertEqual(self.r(f"{self.pol4}/scaling_max_freq"), "1401600")
        self.assertEqual(self.r(f"{self.pol0}/scaling_max_freq"), "1017600")
        self.assertEqual(self.r(f"{self.gpu}/max_freq"), "600000000")

    def test_performance_and_max(self):
        perf.apply("performance")
        self.assertEqual(self.r(f"{self.pol4}/scaling_min_freq"), "1056000")
        self.assertEqual(self.r(f"{self.gpu}/min_freq"), "600000000")
        perf.apply("max")
        self.assertEqual(self.r(f"{self.pol4}/scaling_governor"), "performance")
        self.assertEqual(self.r(f"{self.gpu}/governor"), "performance")
        perf.apply("balanced")
        self.assertEqual(self.r(f"{self.pol4}/scaling_governor"), "schedutil")
        self.assertEqual(self.r(f"{self.pol4}/scaling_min_freq"), "300000")
        self.assertEqual(self.r(f"{self.gpu}/max_freq"), "1050000000")


class TestIrqAndPower(FakeRootCase):
    def test_gic_map(self):
        m = irq.gic_map(fakesys.INTERRUPTS)
        self.assertEqual(m[177], [25])
        self.assertNotIn(-5, m)

    def test_apply(self):
        irq.apply()
        self.assertEqual(self.r("proc/irq/25/smp_affinity_list"), "3")
        self.assertEqual(self.r("proc/irq/40/smp_affinity_list"), "1-2")
        self.assertEqual(self.r("proc/irq/52/smp_affinity_list"), "2")
        self.assertEqual(self.r("proc/irq/11/smp_affinity_list"), "0-7")

    def test_battery_and_temps(self):
        b = power.battery()
        self.assertEqual(b["capacity"], 55)
        self.assertAlmostEqual(b["temp_c"], 31.2)
        self.assertEqual(set(power.soc_temps()), set(power.SOC_ZONES))


class TestState(FakeRootCase):
    def test_validation_and_persistence(self):
        st = state.State()
        self.assertEqual(st.set("led.color", "#FF00aa"), "ff00aa")
        self.assertEqual(st.set("led.color2", "blue"), "0000ff")
        self.assertEqual(st.set("led.brightness", 250), 100)
        with self.assertRaises(ValueError):
            st.set("fan.mode", "turbo")
        with self.assertRaises(KeyError):
            st.set("led.nope", 1)
        st.set("perf.games.n64", "max")
        st.save()
        again = state.State()
        self.assertEqual(again.get("led.color"), "ff00aa")
        self.assertEqual(again.get("perf.games")["n64"], "max")

    def test_corrupt_file_ignored(self):
        p = sysfs.path(state.STATE_FILE)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write('{"led": {"mode": "disco", "brightness": 20}}')
        st = state.State()
        self.assertEqual(st.get("led.mode"), "battery")
        self.assertEqual(st.get("led.brightness"), 20)


class TestDaemon(FakeRootCase):
    def test_commands(self):
        d = hwd.Daemon()
        d.apply_all()
        self.assertEqual(d.handle({"cmd": "set", "key": "led.mode", "value": "static"})["value"], "static")
        self.assertEqual(d.handle({"cmd": "cycle", "key": "fan.mode"})["value"], "quiet")
        self.assertEqual(self.r("sys/class/thermal/thermal_zone1/trip_point_1_temp"), "80000")
        r = d.handle({"cmd": "game-start", "system": "PS2", "pid": None})
        self.assertEqual(r["profile"], "max")
        self.assertEqual(self.r("sys/class/devfreq/5900000.gpu/governor"), "performance")
        r = d.handle({"cmd": "game-end"})
        self.assertEqual(r["profile"], "balanced")
        self.assertFalse(d.handle({"cmd": "bogus"})["ok"])
        d.handle({"cmd": "suspend"})
        self.assertEqual(self.r("sys/class/leds/rgb:l1/brightness"), "0")
        d.handle({"cmd": "resume"})
        self.assertEqual(self.r("sys/class/leds/rgb:l1/brightness"), str(round(255 * 0.6)))

    def test_feedback_flash(self):
        d = hwd.Daemon()
        r = d.handle({"cmd": "cycle", "key": "perf.profile", "feedback": True})
        self.assertEqual(r["value"], "performance")
        self.assertEqual(d.flash_color, (0xff, 0xaa, 0x00))
        self.assertTrue(d.handle({"cmd": "flash", "color": "red", "ms": 200})["ok"])
        self.assertEqual(d.flash_color, (255, 0, 0))

        async def one_frame():
            task = asyncio.create_task(d.led_loop())
            await asyncio.sleep(0.05)
            task.cancel()
        asyncio.run(one_frame())
        self.assertEqual(self.r("sys/class/leds/rgb:l1/multi_intensity"), "255 0 0")

    def test_socket_roundtrip(self):
        sock = os.path.join(self.root, "hwd.sock")

        async def scenario():
            d = hwd.Daemon()
            server = await asyncio.start_unix_server(d.client, path=sock)
            loop = asyncio.get_running_loop()
            old = protocol.SOCKET
            protocol.SOCKET = sock
            try:
                st = await loop.run_in_executor(None, protocol.request, {"cmd": "status"})
                rep = await loop.run_in_executor(
                    None, protocol.request, {"cmd": "set", "key": "perf.profile", "value": "nope"})
            finally:
                protocol.SOCKET = old
                server.close()
                await server.wait_closed()
            return st, rep

        st, rep = asyncio.run(scenario())
        self.assertTrue(st["ok"])
        self.assertEqual(st["status"]["leds"], 18)
        self.assertEqual(st["status"]["battery"]["capacity"], 55)
        json.dumps(st)
        self.assertFalse(rep["ok"])


if __name__ == "__main__":
    unittest.main()
