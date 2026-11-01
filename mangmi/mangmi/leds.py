# SPDX-License-Identifier: GPL-2.0-or-later
"""Analog stick RGB lighting (2x AW20036 grouped as 18 multicolor LEDs).

sysfs: /sys/class/leds/rgb:l1..l9 (left ring), rgb:r1..r9 (right ring),
each with ``multi_intensity`` ("r g b") and ``brightness``.
"""
from __future__ import annotations

import colorsys
import math
import re
from dataclasses import dataclass, field

from . import sysfs

RGB = tuple[int, int, int]
LED_CLASS = "/sys/class/leds"
_NAME = re.compile(r"^rgb:([lr])(\d+)$")


@dataclass
class Led:
    name: str
    side: str          # "l" or "r"
    index: int         # position on the ring, 0-based
    max_brightness: int = 255

    @property
    def base(self) -> str:
        return f"{LED_CLASS}/{self.name}"


@dataclass
class LedRings:
    leds: list[Led] = field(default_factory=list)

    @classmethod
    def discover(cls) -> "LedRings":
        leds = []
        for name in sysfs.listdir(LED_CLASS):
            m = _NAME.match(name)
            if not m:
                continue
            mb = sysfs.read_int(f"{LED_CLASS}/{name}/max_brightness", 255) or 255
            leds.append(Led(name, m.group(1), int(m.group(2)) - 1, mb))
        leds.sort(key=lambda d: (d.side, d.index))
        return cls(leds)

    def __bool__(self) -> bool:
        return bool(self.leds)

    def ring_size(self, side: str) -> int:
        return max((d.index + 1 for d in self.leds if d.side == side), default=1)

    def set_brightness(self, percent: int) -> None:
        for d in self.leds:
            sysfs.write(f"{d.base}/brightness", round(d.max_brightness * percent / 100))

    def show(self, colors: list[RGB]) -> None:
        for d, (r, g, b) in zip(self.leds, colors):
            scale = d.max_brightness / 255
            sysfs.write(f"{d.base}/multi_intensity",
                        f"{round(r * scale)} {round(g * scale)} {round(b * scale)}")


def hex_to_rgb(h: str) -> RGB:
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return round(r * 255), round(g * 255), round(b * 255)


def scale(c: RGB, k: float) -> RGB:
    k = max(0.0, min(1.0, k))
    return round(c[0] * k), round(c[1] * k), round(c[2] * k)


def period(speed: int, slow: float, fast: float) -> float:
    """Map speed 1..100 % onto a period between ``slow`` and ``fast`` seconds."""
    s = max(1, min(100, speed)) / 100
    return slow + (fast - slow) * s


@dataclass
class Context:
    battery: int | None = None      # percent
    charging: bool = False
    full: bool = False
    temp_c: float | None = None     # hottest SoC zone


ANIMATED = {"breath", "rainbow", "wave"}


def is_animated(mode: str, ctx: Context) -> bool:
    if mode in ANIMATED:
        return True
    if mode == "battery":
        return ctx.charging or (ctx.battery is not None and ctx.battery < 10)
    return False


def battery_color(pct: int) -> RGB:
    # red (0 deg) at <=5 %, green (120 deg) at >=80 %
    k = (min(max(pct, 5), 80) - 5) / 75
    return hsv(k / 3)


def thermal_color(temp: float) -> RGB:
    # blue (210 deg) when cool (<=45 C) -> red (0 deg) when hot (>=85 C)
    k = (min(max(temp, 45.0), 85.0) - 45.0) / 40.0
    return hsv((1 - k) * 210 / 360)


def frame(rings: LedRings, led: dict, t: float, ctx: Context) -> list[RGB]:
    """Colors for every LED at time ``t`` (seconds)."""
    mode = led["mode"]
    c1 = hex_to_rgb(led["color"])
    c2 = hex_to_rgb(led["color2"]) if led.get("color2") else c1
    speed = int(led.get("speed", 40))
    out: list[RGB] = []

    for d in rings.leds:
        base = c1 if d.side == "l" else c2
        if mode == "off":
            c = (0, 0, 0)
        elif mode == "static":
            c = base
        elif mode == "breath":
            p = period(speed, 6.0, 1.2)
            c = scale(base, 0.08 + 0.92 * (0.5 - 0.5 * math.cos(2 * math.pi * t / p)))
        elif mode == "rainbow":
            c = hsv(t / period(speed, 14.0, 1.5))
        elif mode == "wave":
            n = rings.ring_size(d.side)
            c = hsv(t / period(speed, 8.0, 1.0) + d.index / n + (0.5 if d.side == "r" else 0))
        elif mode == "battery":
            pct = ctx.battery if ctx.battery is not None else 100
            c = (0, 255, 64) if ctx.full else battery_color(pct)
            if ctx.charging and not ctx.full:
                c = scale(c, 0.25 + 0.75 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 3.0)))
            elif pct < 10:
                c = c if int(t * 2) % 2 == 0 else (0, 0, 0)
        elif mode == "thermal":
            c = thermal_color(ctx.temp_c if ctx.temp_c is not None else 40.0)
        else:
            c = base
        out.append(c)
    return out
