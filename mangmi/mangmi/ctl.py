# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-ctl - control lighting, fan and performance of the Mangmi Air X.

Examples:
  mangmi-ctl status
  mangmi-ctl led rainbow --speed 60
  mangmi-ctl led static --color ff0040 --color2 00aaff --brightness 80
  mangmi-ctl led brightness 30
  mangmi-ctl fan quiet
  mangmi-ctl perf performance
  mangmi-ctl perf game ps2 max      # profile used while PS2 games run
  mangmi-ctl cycle led              # next LED mode (handy for hotkeys)
  mangmi-ctl flash ff0000           # flash the sticks red (feedback for scripts)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .protocol import DaemonUnavailable, request
from .state import FAN_MODES, LED_MODES, PERF_PROFILES


def _req(msg: dict) -> dict:
    reply = request(msg)
    if not reply.get("ok"):
        raise SystemExit(f"mangmi-ctl: {reply.get('error', 'request failed')}")
    return reply


def _set(key: str, value) -> None:
    r = _req({"cmd": "set", "key": key, "value": value})
    print(f"{key} = {r['value']}")


def _fmt_status(st: dict) -> str:
    s = st["settings"]
    b = st.get("battery") or {}
    lines = [
        f"Mangmi hardware daemon {st['version']}",
        f"  battery      {b.get('capacity', '?')}% ({b.get('status', '?')})"
        + (f", {b['temp_c']:.1f} C" if "temp_c" in b else ""),
        "  temperatures " + (", ".join(f"{k.replace('-thermal', '')} {v:.0f} C"
                                       for k, v in sorted(st.get("temps_c", {}).items())) or "n/a"),
        f"  fan          {s['fan']['mode']} ("
        + {True: "running", False: "stopped", None: "unknown"}[st.get("fan_running")] + ")",
        f"  performance  {s['perf']['profile']} (active: {st.get('active_profile')})",
        f"  stick LEDs   {s['led']['mode']}, color #{s['led']['color']}"
        + (f"/#{s['led']['color2']}" if s['led'].get('color2') else "")
        + f", brightness {s['led']['brightness']}%, speed {s['led']['speed']}%"
        + ("" if st.get("leds") else " (no LEDs detected)"),
    ]
    if st.get("game"):
        lines.append(f"  game         {st['game'].get('name') or '?'} [{st['game'].get('system')}]")
    for kind in ("little", "big", "gpu"):
        f = st.get("freqs", {}).get(kind)
        if f:
            cur = f.get("cur_khz") or (f.get("cur_hz") or 0) // 1000
            mx = f.get("max_khz") or (f.get("max_hz") or 0) // 1000
            lines.append(f"  {kind:<12} {f.get('governor')} {cur / 1000:.0f}/{mx / 1000:.0f} MHz")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mangmi-ctl", description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="show hardware state")
    st.add_argument("--json", action="store_true")

    led = sub.add_parser("led", help="stick lighting")
    led.add_argument("mode", choices=LED_MODES + ("brightness", "color"))
    led.add_argument("value", nargs="?", help="value for brightness/color")
    led.add_argument("--color")
    led.add_argument("--color2", help="right stick color ('same' = like left)")
    led.add_argument("--brightness", type=int)
    led.add_argument("--speed", type=int)

    fan = sub.add_parser("fan", help="fan mode")
    fan.add_argument("mode", choices=FAN_MODES)

    pf = sub.add_parser("perf", help="performance profile")
    pf.add_argument("profile", choices=PERF_PROFILES + ("game",))
    pf.add_argument("system", nargs="?")
    pf.add_argument("system_profile", nargs="?", choices=PERF_PROFILES)

    cy = sub.add_parser("cycle", help="switch to the next mode")
    cy.add_argument("what", choices=("led", "fan", "perf"))

    fl = sub.add_parser("flash", help="flash the stick LEDs once")
    fl.add_argument("color", nargs="?", default="ffffff")
    fl.add_argument("--ms", type=int, default=600)

    gs = sub.add_parser("game-start", help="(used by launchers) a game started")
    gs.add_argument("system")
    gs.add_argument("--pid", type=int, default=None)
    gs.add_argument("--name", default=None)
    sub.add_parser("game-end", help="(used by launchers) the game ended")
    for c in ("suspend", "resume", "reload"):
        sub.add_parser(c, help=f"(internal) {c}")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "status":
            st = _req({"cmd": "status"})["status"]
            print(json.dumps(st, indent=2) if a.json else _fmt_status(st))
        elif a.cmd == "led":
            if a.mode == "brightness":
                _set("led.brightness", a.value if a.value is not None else a.brightness)
            elif a.mode == "color":
                _set("led.color", a.value or a.color)
            else:
                for key, val in (("color", a.color), ("color2", a.color2),
                                 ("brightness", a.brightness), ("speed", a.speed)):
                    if val is not None:
                        _set(f"led.{key}", val)
                _set("led.mode", a.mode)
        elif a.cmd == "fan":
            _set("fan.mode", a.mode)
        elif a.cmd == "perf":
            if a.profile == "game":
                if not (a.system and a.system_profile):
                    ap.error("usage: mangmi-ctl perf game <system> <profile>")
                _set(f"perf.games.{a.system.lower()}", a.system_profile)
            else:
                _set("perf.profile", a.profile)
        elif a.cmd == "cycle":
            key = {"led": "led.mode", "fan": "fan.mode", "perf": "perf.profile"}[a.what]
            r = _req({"cmd": "cycle", "key": key})
            print(f"{key} = {r['value']}")
        elif a.cmd == "flash":
            _req({"cmd": "flash", "color": a.color, "ms": a.ms})
        elif a.cmd == "game-start":
            _req({"cmd": "game-start", "system": a.system, "pid": a.pid or os.getppid(), "name": a.name})
        else:
            _req({"cmd": a.cmd})
    except DaemonUnavailable as e:
        print(f"mangmi-ctl: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
