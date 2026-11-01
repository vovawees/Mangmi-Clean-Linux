# SPDX-License-Identifier: GPL-2.0-or-later
"""Battery and temperature readings."""
from __future__ import annotations

from . import sysfs

PS = "/sys/class/power_supply"


def battery_dir() -> str | None:
    for name in sysfs.listdir(PS):
        if sysfs.read(f"{PS}/{name}/type") == "Battery":
            return f"{PS}/{name}"
    return None


def battery() -> dict:
    d = battery_dir()
    if not d:
        return {}
    info = {
        "capacity": sysfs.read_int(f"{d}/capacity"),
        "status": sysfs.read(f"{d}/status", "Unknown"),
    }
    temp = sysfs.read_int(f"{d}/temp")
    if temp is not None:
        info["temp_c"] = temp / 10
    for key, attr in (("voltage_v", "voltage_now"), ("current_a", "current_now"), ("power_w", "power_now")):
        v = sysfs.read_int(f"{d}/{attr}")
        if v is not None:
            info[key] = round(v / 1_000_000, 3)
    return info


THERMAL = "/sys/class/thermal"
SOC_ZONES = ("cpu0123-thermal", "cpu45-thermal", "cpu67-thermal", "gpu-thermal")


def zones() -> dict[str, str]:
    """thermal zone type -> sysfs dir"""
    out = {}
    for name in sysfs.listdir(THERMAL):
        if name.startswith("thermal_zone"):
            t = sysfs.read(f"{THERMAL}/{name}/type")
            if t:
                out.setdefault(t, f"{THERMAL}/{name}")
    return out


def soc_temps() -> dict[str, float]:
    out = {}
    for t, d in zones().items():
        if t in SOC_ZONES:
            v = sysfs.read_int(f"{d}/temp")
            if v is not None:
                out[t] = v / 1000
    return out
