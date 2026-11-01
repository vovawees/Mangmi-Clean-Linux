# SPDX-License-Identifier: GPL-2.0-or-later
"""Fan control through the thermal framework.

The Mangmi Air X fan is an on/off ``gpio-fan`` cooling device bound to
"active" trip points of the CPU, GPU and battery thermal zones (70 C / 40 C by
default). Fan modes move those trip points (CONFIG_THERMAL_WRITABLE_TRIPS), so
the kernel keeps doing the actual control - no polling loop in user space and
passive (throttling) trips are never touched.
"""
from __future__ import annotations

import json
import logging
import os

from . import sysfs
from .power import THERMAL

log = logging.getLogger("mangmi.fan")

DEFAULTS_FILE = "/run/mangmi/fan-defaults.json"
FAN_CDEV_TYPES = ("gpio-fan", "gpio_fan", "fan")

# mode -> (offset in C relative to the device tree value, absolute minimum C)
MODES = {
    "auto": (0, None),
    "quiet": (+10, None),
    "cool": (-15, 45),
    "max": (None, 30),   # None offset: pin the trip to the minimum -> always on
}
MAX_TRIP_C = 85   # never delay the fan beyond this


def fan_cdevs() -> set[str]:
    out = set()
    for name in sysfs.listdir(THERMAL):
        if name.startswith("cooling_device") and \
                (sysfs.read(f"{THERMAL}/{name}/type") or "") in FAN_CDEV_TYPES:
            out.add(name)
    return out


def fan_trips() -> list[tuple[str, int]]:
    """[(zone dir, trip index)] for every active trip that switches the fan."""
    cdevs = fan_cdevs()
    found: set[tuple[str, int]] = set()
    for zone in sysfs.listdir(THERMAL):
        if not zone.startswith("thermal_zone"):
            continue
        zdir = f"{THERMAL}/{zone}"
        for entry in sysfs.listdir(zdir):
            if not entry.startswith("cdev") or "_" in entry:
                continue
            target = os.path.basename(os.path.realpath(sysfs.path(f"{zdir}/{entry}")))
            if target not in cdevs:
                continue
            trip = sysfs.read_int(f"{zdir}/{entry}_trip_point")
            if trip is None:
                continue
            if sysfs.read(f"{zdir}/trip_point_{trip}_type") == "active":
                found.add((zdir, trip))
    return sorted(found)


def _load_defaults(trips: list[tuple[str, int]]) -> dict[str, int]:
    full = sysfs.path(DEFAULTS_FILE)
    try:
        with open(full, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        saved = {}
    changed = False
    for zdir, trip in trips:
        key = f"{zdir}:{trip}"
        if key not in saved:
            v = sysfs.read_int(f"{zdir}/trip_point_{trip}_temp")
            if v is not None:
                saved[key] = v
                changed = True
    if changed:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            json.dump(saved, fh)
    return saved


def target_temp(default_mc: int, mode: str) -> int:
    offset, minimum = MODES[mode]
    if offset is None:
        return (minimum or 30) * 1000
    t = default_mc + offset * 1000
    if minimum is not None:
        t = max(t, minimum * 1000)
    return min(t, max(default_mc, MAX_TRIP_C * 1000))


def apply(mode: str) -> int:
    """Apply a fan mode; returns the number of trip points changed."""
    if mode not in MODES:
        raise ValueError(mode)
    trips = fan_trips()
    defaults = _load_defaults(trips)
    n = 0
    for zdir, trip in trips:
        base = defaults.get(f"{zdir}:{trip}")
        if base is None:
            continue
        if sysfs.write(f"{zdir}/trip_point_{trip}_temp", target_temp(base, mode), force=True):
            n += 1
        else:
            log.warning("cannot write %s trip %d (kernel without writable trips?)", zdir, trip)
    return n


def is_running() -> bool | None:
    states = [sysfs.read_int(f"{THERMAL}/{c}/cur_state") for c in fan_cdevs()]
    states = [s for s in states if s is not None]
    return any(s > 0 for s in states) if states else None
