# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a fake Mangmi Air X sysfs/procfs tree for tests."""
from __future__ import annotations

import os

INTERRUPTS = """\
           CPU0       CPU1       CPU2       CPU3       CPU4       CPU5       CPU6       CPU7
 11:      10000      10000      10000      10000      10000      10000      10000      10000     GICv3  27 Level     arch_timer
 25:        500          0          0          0          0          0          0          0     GICv3 209 Level     kgsl-3d0
 26:        100          0          0          0          0          0          0          0     GICv3 218 Level     msm_mdss
 40:       9000          0          0          0          0          0          0          0     GICv3 380 Level     mmc0
 41:         10          0          0          0          0          0          0          0     GICv3 382 Level     mmc1
 52:         20          0          0          0          0          0          0          0     GICv3 359 Level     mangmi-joypad
 60:          5          0          0          0          0          0          0          0   pmic_arb 1 Edge      pm6125_resin
"""


def _w(root: str, rel: str, value: object) -> None:
    p = os.path.join(root, rel.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(f"{value}\n")


def build(root: str) -> None:
    for side in "lr":
        for i in range(1, 10):
            base = f"sys/class/leds/rgb:{side}{i}"
            _w(root, f"{base}/max_brightness", 255)
            _w(root, f"{base}/brightness", 0)
            _w(root, f"{base}/multi_intensity", "0 0 0")
            _w(root, f"{base}/multi_index", "red green blue")
    _w(root, "sys/class/leds/mmc0::/brightness", 0)   # unrelated LED

    bat = "sys/class/power_supply/battery"
    _w(root, f"{bat}/type", "Battery")
    _w(root, f"{bat}/capacity", 55)
    _w(root, f"{bat}/status", "Discharging")
    _w(root, f"{bat}/temp", 312)
    _w(root, "sys/class/power_supply/usb/type", "USB")

    th = "sys/class/thermal"
    _w(root, f"{th}/cooling_device0/type", "gpio-fan")
    _w(root, f"{th}/cooling_device0/cur_state", 0)
    _w(root, f"{th}/cooling_device1/type", "cpufreq-cpu4")
    _w(root, f"{th}/cooling_device1/cur_state", 0)
    zones = [("cpu0123-thermal", 70000), ("cpu45-thermal", 70000), ("cpu67-thermal", 70000),
             ("gpu-thermal", 70000), ("battery-thermal", 40000), ("pm6125-thermal", None)]
    for n, (ztype, fan_trip) in enumerate(zones):
        z = f"{th}/thermal_zone{n}"
        _w(root, f"{z}/type", ztype)
        _w(root, f"{z}/temp", 48000 + n * 1000)
        _w(root, f"{z}/trip_point_0_type", "passive")
        _w(root, f"{z}/trip_point_0_temp", 95000)
        if fan_trip:
            _w(root, f"{z}/trip_point_1_type", "active")
            _w(root, f"{z}/trip_point_1_temp", fan_trip)
            os.symlink("../cooling_device0", os.path.join(root, z, "cdev0"))
            _w(root, f"{z}/cdev0_trip_point", 1)
            # the passive trip throttles the CPU - must never be touched
            os.symlink("../cooling_device1", os.path.join(root, z, "cdev1"))
            _w(root, f"{z}/cdev1_trip_point", 0)

    cf = "sys/devices/system/cpu/cpufreq"
    little = [300000, 614400, 864000, 1017600, 1305600, 1420800, 1612800, 1804800]
    big = [300000, 652800, 902400, 1056000, 1401600, 1536000, 1804800, 2016000]
    for pol, freqs in (("policy0", little), ("policy4", big)):
        _w(root, f"{cf}/{pol}/scaling_available_frequencies", " ".join(map(str, freqs)))
        _w(root, f"{cf}/{pol}/scaling_available_governors", "ondemand userspace powersave performance schedutil")
        _w(root, f"{cf}/{pol}/scaling_governor", "schedutil")
        _w(root, f"{cf}/{pol}/scaling_min_freq", freqs[0])
        _w(root, f"{cf}/{pol}/scaling_max_freq", freqs[-1])
        _w(root, f"{cf}/{pol}/scaling_cur_freq", freqs[2])
        _w(root, f"{cf}/{pol}/cpuinfo_min_freq", freqs[0])
        _w(root, f"{cf}/{pol}/cpuinfo_max_freq", freqs[-1])

    gpu = "sys/class/devfreq/5900000.gpu"
    gf = [320000000, 465000000, 600000000, 745000000, 820000000, 900000000, 950000000, 980000000, 1050000000]
    _w(root, f"{gpu}/available_frequencies", " ".join(map(str, gf)))
    _w(root, f"{gpu}/available_governors", "userspace powersave performance simple_ondemand")
    _w(root, f"{gpu}/governor", "simple_ondemand")
    _w(root, f"{gpu}/min_freq", gf[0])
    _w(root, f"{gpu}/max_freq", gf[-1])
    _w(root, f"{gpu}/cur_freq", gf[0])
    _w(root, "sys/class/devfreq/soc@0:qcom,cpu-bwmon/available_frequencies", "100 200")

    _w(root, "proc/interrupts", INTERRUPTS.rstrip("\n"))
    for irq in (11, 25, 26, 40, 41, 52, 60):
        _w(root, f"proc/irq/{irq}/smp_affinity_list", "0-7")


def read(root: str, rel: str) -> str:
    with open(os.path.join(root, rel.lstrip("/"))) as fh:
        return fh.read().strip()
