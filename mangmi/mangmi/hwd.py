# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-hwd - Mangmi Air X hardware daemon (runs as root).

* analog stick RGB effects (static, breath, rainbow, wave, battery, thermal)
* fan modes (auto / quiet / cool / max) via thermal trip points
* CPU/GPU performance profiles, with per-system overrides while a game runs
* IRQ affinity, suspend/resume handling
Clients talk to it with ``mangmi-ctl`` over /run/mangmi/hwd.sock.
"""
from __future__ import annotations

import argparse
import asyncio
import grp
import json
import logging
import os
import signal
import time

from . import __version__, fan, irq, leds, perf, power, sysfs
from .protocol import SOCKET
from .state import FAN_MODES, LED_MODES, PERF_PROFILES, State

log = logging.getLogger("mangmi.hwd")

FPS = 25
CYCLES = {"led.mode": LED_MODES, "fan.mode": FAN_MODES, "perf.profile": PERF_PROFILES}
# Colour the sticks flash after a hotkey changed a setting (instant feedback in any app).
FEEDBACK = {
    "perf.profile": {"powersave": "00ff40", "balanced": "00aaff", "performance": "ffaa00", "max": "ff0000"},
    "fan.mode": {"auto": "ffffff", "quiet": "00ff40", "cool": "00ffff", "max": "ff0000"},
}
FLASH_MS = 600


class Daemon:
    def __init__(self, state_file: str | None = None):
        self.state = State(state_file) if state_file else State()
        self.rings = leds.LedRings.discover()
        self.ctx = leds.Context()
        self.game: dict | None = None
        self.suspended = False
        self.wake = asyncio.Event()
        self.t0 = time.monotonic()
        self.active_profile: str | None = None
        self.flash_color: leds.RGB | None = None
        self.flash_until = 0.0

    # ---- hardware application -------------------------------------------------
    def apply_led_static_parts(self) -> None:
        if not self.rings:
            return
        led = self.state.data["led"]
        on = led["mode"] != "off" and not self.suspended
        self.rings.set_brightness(led["brightness"] if on else 0)

    def apply_fan(self) -> None:
        n = fan.apply(self.state.data["fan"]["mode"])
        log.info("fan mode %s (%d trip points)", self.state.data["fan"]["mode"], n)

    def effective_profile(self) -> str:
        if self.game:
            sysname = self.game.get("system", "")
            override = self.state.data["perf"]["games"].get(sysname)
            if override:
                return override
        return self.state.data["perf"]["profile"]

    def apply_perf(self, force: bool = False) -> None:
        prof = self.effective_profile()
        if prof != self.active_profile or force:
            res = perf.apply(prof)
            self.active_profile = prof
            log.info("performance profile %s: %s", prof, res)

    def refresh_context(self) -> None:
        b = power.battery()
        self.ctx.battery = b.get("capacity")
        status = (b.get("status") or "").lower()
        self.ctx.charging = status == "charging"
        self.ctx.full = status == "full"
        temps = power.soc_temps()
        self.ctx.temp_c = max(temps.values()) if temps else None

    def apply_all(self) -> None:
        self.apply_led_static_parts()
        self.apply_fan()
        self.apply_perf(force=True)
        self.wake.set()

    # ---- loops ------------------------------------------------------------------
    async def led_loop(self) -> None:
        if not self.rings:
            log.info("no stick LEDs found, LED effects disabled")
            return
        while True:
            led = self.state.data["led"]
            now = time.monotonic()
            if self.flash_color and now < self.flash_until and not self.suspended:
                self.rings.set_brightness(max(led["brightness"], 50))
                self.rings.show([self.flash_color] * len(self.rings.leds))
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), self.flash_until - now)
                except TimeoutError:
                    pass
                continue
            if self.flash_color:
                self.flash_color = None
                self.apply_led_static_parts()
            if self.suspended or led["mode"] == "off":
                self.rings.set_brightness(0)
                animated = False
            else:
                t = time.monotonic() - self.t0
                self.rings.show(leds.frame(self.rings, led, t, self.ctx))
                animated = leds.is_animated(led["mode"], self.ctx)
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), 1 / FPS if animated else 5.0)
            except TimeoutError:
                pass

    async def monitor_loop(self) -> None:
        last_battery_state = None
        while True:
            self.refresh_context()
            snap = (self.ctx.battery, self.ctx.charging, self.ctx.full)
            if snap != last_battery_state:
                last_battery_state = snap
                self.wake.set()
            if self.game and self.game.get("pid") and not os.path.exists(f"/proc/{self.game['pid']}"):
                log.info("game process %s gone, restoring profile", self.game["pid"])
                self.game = None
                self.apply_perf()
            await asyncio.sleep(5)

    # ---- commands -------------------------------------------------------------------
    def status(self) -> dict:
        self.refresh_context()
        return {
            "version": __version__,
            "settings": self.state.data,
            "active_profile": self.active_profile,
            "game": self.game,
            "battery": power.battery(),
            "temps_c": power.soc_temps(),
            "fan_running": fan.is_running(),
            "freqs": perf.snapshot(),
            "leds": len(self.rings.leds),
        }

    def flash(self, color: str, ms: int = FLASH_MS) -> None:
        if not self.rings:
            return
        self.flash_color = leds.hex_to_rgb(color)
        self.flash_until = time.monotonic() + max(100, min(int(ms), 5000)) / 1000
        self.wake.set()

    def handle(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        if cmd == "flash":
            from .state import parse_color
            self.flash(parse_color(msg.get("color", "ffffff")), msg.get("ms", FLASH_MS))
            return {"ok": True}
        if cmd == "status":
            return {"ok": True, "status": self.status()}
        if cmd == "get":
            return {"ok": True, "value": self.state.get(msg["key"])}
        if cmd in ("set", "cycle"):
            key = msg["key"]
            if cmd == "cycle":
                options = CYCLES[key]
                cur = self.state.get(key)
                value = options[(options.index(cur) + 1) % len(options)] if cur in options else options[0]
            else:
                value = msg["value"]
            new = self.state.set(key, value)
            self.state.save()
            section = key.split(".")[0]
            if section == "led":
                self.apply_led_static_parts()
                self.wake.set()
            elif section == "fan":
                self.apply_fan()
            elif section == "perf":
                self.apply_perf()
            if msg.get("feedback"):
                color = FEEDBACK.get(key, {}).get(new)
                if color:
                    self.flash(color)
            return {"ok": True, "key": key, "value": new}
        if cmd == "game-start":
            self.game = {"system": str(msg.get("system", "")).lower(), "pid": msg.get("pid"),
                         "name": msg.get("name")}
            self.apply_perf()
            return {"ok": True, "profile": self.active_profile}
        if cmd == "game-end":
            self.game = None
            self.apply_perf()
            return {"ok": True, "profile": self.active_profile}
        if cmd == "suspend":
            self.suspended = True
            self.apply_led_static_parts()
            self.wake.set()
            return {"ok": True}
        if cmd == "resume":
            self.suspended = False
            sysfs.forget()          # hardware may have lost its state
            self.apply_all()
            return {"ok": True}
        if cmd == "reload":
            self.state.load()
            self.apply_all()
            return {"ok": True}
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    async def client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            try:
                reply = self.handle(json.loads(line))
            except (KeyError, ValueError, TypeError) as e:
                reply = {"ok": False, "error": str(e)}
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    async def serve(self, sock_path: str, group: str | None) -> None:
        os.makedirs(os.path.dirname(sock_path), exist_ok=True)
        try:
            os.unlink(sock_path)
        except FileNotFoundError:
            pass
        server = await asyncio.start_unix_server(self.client, path=sock_path)
        mode = 0o660
        if group:
            try:
                os.chown(sock_path, 0, grp.getgrnam(group).gr_gid)
            except (KeyError, PermissionError):
                mode = 0o666
        os.chmod(sock_path, mode)

        irq.apply()
        self.refresh_context()
        self.apply_all()
        log.info("mangmi-hwd %s ready (%d LEDs) on %s", __version__, len(self.rings.leds), sock_path)

        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        tasks = [asyncio.create_task(self.led_loop()), asyncio.create_task(self.monitor_loop())]
        async with server:
            await stop.wait()
        for t in tasks:
            t.cancel()
        if self.rings:
            self.rings.set_brightness(0)
        log.info("stopped")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mangmi-hwd", description=__doc__.splitlines()[0])
    ap.add_argument("--socket", default=SOCKET)
    ap.add_argument("--group", default=os.environ.get("MANGMI_HWD_GROUP", "wheel"))
    ap.add_argument("--state", default=None, help="settings file (default /var/lib/mangmi/hwd.json)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(name)s: %(message)s")
    asyncio.run(Daemon(args.state).serve(args.socket, args.group))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
