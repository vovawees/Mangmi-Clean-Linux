# SPDX-License-Identifier: GPL-2.0-or-later
"""Persistent settings with defaults and validation."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from typing import Any

from . import sysfs

log = logging.getLogger("mangmi.state")

STATE_FILE = "/var/lib/mangmi/hwd.json"

LED_MODES = ("off", "static", "breath", "rainbow", "wave", "battery", "thermal")
FAN_MODES = ("auto", "quiet", "cool", "max")
PERF_PROFILES = ("powersave", "balanced", "performance", "max")

DEFAULTS: dict[str, Any] = {
    "led": {
        "mode": "battery",
        "color": "00aaff",     # left stick (or both)
        "color2": "",          # right stick; empty = same as color
        "brightness": 60,      # percent
        "speed": 40,           # percent, animation speed
    },
    "fan": {"mode": "auto"},
    "perf": {
        "profile": "balanced",
        # Per-system overrides applied while a game runs (ES-DE system names).
        "games": {
            "ps2": "max", "gc": "max", "wii": "max", "3ds": "performance",
            "saturn": "performance", "dreamcast": "performance",
            "psp": "performance", "n64": "performance", "nds": "performance",
            "psx": "balanced",
        },
    },
}

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_color(value: str) -> str:
    m = _HEX.match(value.strip())
    if not m:
        named = {
            "red": "ff0000", "green": "00ff00", "blue": "0000ff", "white": "ffffff",
            "cyan": "00ffff", "magenta": "ff00ff", "yellow": "ffff00",
            "orange": "ff6000", "purple": "8000ff", "pink": "ff3080",
        }
        if value.lower() in named:
            return named[value.lower()]
        raise ValueError(f"bad color {value!r} (use RRGGBB or a name)")
    return m.group(1).lower()


def _clamp_pct(v: Any) -> int:
    return max(0, min(100, int(v)))


VALIDATORS = {
    "led.mode": lambda v: _choice(v, LED_MODES),
    "led.color": parse_color,
    "led.color2": lambda v: "" if str(v) in ("", "same", "none") else parse_color(str(v)),
    "led.brightness": _clamp_pct,
    "led.speed": lambda v: max(1, _clamp_pct(v)),
    "fan.mode": lambda v: _choice(v, FAN_MODES),
    "perf.profile": lambda v: _choice(v, PERF_PROFILES),
}


def _choice(v: Any, options: tuple[str, ...]) -> str:
    v = str(v).lower()
    if v not in options:
        raise ValueError(f"{v!r} is not one of {', '.join(options)}")
    return v


class State:
    def __init__(self, file: str = STATE_FILE):
        self.file = file
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(sysfs.path(self.file), encoding="utf-8") as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            return
        for key, validate in VALIDATORS.items():
            section, name = key.split(".")
            if name in saved.get(section, {}):
                try:
                    self.data[section][name] = validate(saved[section][name])
                except (ValueError, TypeError):
                    log.warning("ignoring invalid saved %s=%r", key, saved[section][name])
        games = saved.get("perf", {}).get("games")
        if isinstance(games, dict):
            for system, prof in games.items():
                if prof in PERF_PROFILES:
                    self.data["perf"]["games"][str(system)] = prof

    def save(self) -> None:
        full = sysfs.path(self.file)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix=".hwd.")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)
        os.replace(tmp, full)

    def get(self, key: str) -> Any:
        node: Any = self.data
        for part in key.split("."):
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> Any:
        if key.startswith("perf.games."):
            system = key.split(".", 2)[2]
            self.data["perf"]["games"][system] = _choice(value, PERF_PROFILES)
            return self.data["perf"]["games"][system]
        if key not in VALIDATORS:
            raise KeyError(f"unknown setting {key!r}")
        section, name = key.split(".")
        self.data[section][name] = VALIDATORS[key](value)
        return self.data[section][name]
