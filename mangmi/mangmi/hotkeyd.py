# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-hotkeyd - system hotkeys of the Mangmi Air X (runs in the user session).

All combos start with the Guide (Mangmi) button held:

  Guide + D-pad Up / Down      screen brightness
  Guide + D-pad Right          next performance profile (sticks flash the colour)
  Guide + D-pad Left           next fan mode
  Guide + R3                   next stick lighting mode
  Guide + L3                   gamepad <-> mouse & keyboard
  Guide + Select (hold 1.5 s)  switch console <-> desktop
  Guide + Start  (hold 1.5 s)  force-close the running game

RetroArch uses Guide + face buttons / shoulders / Start, so the sets never overlap.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import time

from .protocol import DaemonUnavailable, request

log = logging.getLogger("mangmi.hotkeyd")

HOLD_SECONDS = 1.5
TAP = {
    "up": "brightness-up",
    "down": "brightness-down",
    "right": "perf-next",
    "left": "fan-next",
    "r3": "led-next",
    "l3": "input-toggle",
}
HOLD = {"select": "mode-toggle", "start": "game-close"}


class Combos:
    """Pure combo state machine: feed button edges, get the actions to run."""

    def __init__(self) -> None:
        self.down: set[str] = set()
        self.pending: dict[str, float] = {}

    def feed(self, name: str, pressed: bool, t: float) -> list[str]:
        if pressed:
            if name in self.down:
                return []
            self.down.add(name)
            if name == "guide" or "guide" not in self.down:
                return []
            if name in HOLD:
                self.pending[name] = t + HOLD_SECONDS
            return [TAP[name]] if name in TAP else []
        self.down.discard(name)
        if name == "guide":
            self.pending.clear()
        else:
            self.pending.pop(name, None)
        return []

    def due(self, t: float) -> list[str]:
        fired = [n for n, deadline in self.pending.items() if t >= deadline]
        for n in fired:
            del self.pending[n]
        return [HOLD[n] for n in fired]

    def next_deadline(self) -> float | None:
        return min(self.pending.values()) if self.pending else None


def _run(*argv: str) -> None:
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as e:
        log.warning("cannot run %s: %s", argv[0], e)


def _hwd(key: str) -> None:
    try:
        request({"cmd": "cycle", "key": key, "feedback": True}, timeout=2)
    except (DaemonUnavailable, OSError, ValueError) as e:
        log.warning("mangmi-hwd: %s", e)


def perform(action: str) -> None:
    log.info("action %s", action)
    if action == "brightness-up":
        _run("brightnessctl", "-q", "-e4", "-n2", "set", "8%+")
    elif action == "brightness-down":
        _run("brightnessctl", "-q", "-e4", "-n2", "set", "8%-")
    elif action == "perf-next":
        _hwd("perf.profile")
    elif action == "fan-next":
        _hwd("fan.mode")
    elif action == "led-next":
        _hwd("led.mode")
    elif action == "input-toggle":
        _run("mangmi-input", "toggle")
    elif action == "mode-toggle":
        _run("mangmi-mode", "toggle")
    elif action == "game-close":
        _run("mangmi-run", "--stop")


class Reader:
    """Reads gamepads with python-evdev and drives a Combos instance per device."""

    def __init__(self) -> None:
        import evdev  # deferred: unit tests do not need it
        self.evdev = evdev
        e = evdev.ecodes
        self.buttons = {
            e.BTN_MODE: "guide", e.BTN_SELECT: "select", e.BTN_START: "start",
            e.BTN_THUMBL: "l3", e.BTN_THUMBR: "r3",
            e.BTN_DPAD_UP: "up", e.BTN_DPAD_DOWN: "down",
            e.BTN_DPAD_LEFT: "left", e.BTN_DPAD_RIGHT: "right",
        }
        self.hats = {e.ABS_HAT0X: ("left", "right"), e.ABS_HAT0Y: ("up", "down")}
        self.open: dict[str, asyncio.Task] = {}

    def is_gamepad(self, dev) -> bool:
        e = self.evdev.ecodes
        keys = dev.capabilities().get(e.EV_KEY, [])
        return e.BTN_MODE in keys and e.BTN_SOUTH in keys

    async def watch(self, dev) -> None:
        e = self.evdev.ecodes
        combos = Combos()
        timer: asyncio.Task | None = None

        async def fire_later(delay: float) -> None:
            await asyncio.sleep(max(0.0, delay))
            for a in combos.due(time.monotonic()):
                perform(a)

        log.info("watching %s (%s)", dev.path, dev.name)
        try:
            async for ev in dev.async_read_loop():
                now = time.monotonic()
                edges: list[tuple[str, bool]] = []
                if ev.type == e.EV_KEY and ev.code in self.buttons and ev.value in (0, 1):
                    edges.append((self.buttons[ev.code], ev.value == 1))
                elif ev.type == e.EV_ABS and ev.code in self.hats:
                    neg, pos = self.hats[ev.code]
                    edges += [(neg, ev.value < 0), (pos, ev.value > 0)]
                for name, pressed in edges:
                    for a in combos.feed(name, pressed, now):
                        perform(a)
                if timer:
                    timer.cancel()
                    timer = None
                deadline = combos.next_deadline()
                if deadline is not None:
                    timer = asyncio.create_task(fire_later(deadline - now))
        except OSError:
            log.info("%s disappeared", dev.path)
        finally:
            if timer:
                timer.cancel()
            self.open.pop(dev.path, None)

    async def run(self) -> None:
        while True:
            for path in self.evdev.list_devices():
                if path in self.open:
                    continue
                try:
                    dev = self.evdev.InputDevice(path)
                except OSError:
                    continue
                if self.is_gamepad(dev):
                    self.open[path] = asyncio.create_task(self.watch(dev))
                else:
                    dev.close()
            await asyncio.sleep(3)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mangmi-hotkeyd", description=__doc__.splitlines()[0],
                                 epilog="\n".join(__doc__.splitlines()[2:]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(name)s: %(message)s")
    try:
        asyncio.run(Reader().run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
