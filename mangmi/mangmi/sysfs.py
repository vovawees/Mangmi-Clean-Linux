# SPDX-License-Identifier: GPL-2.0-or-later
"""Tiny sysfs/procfs access layer.

All paths go through :func:`path`, which prefixes ``$MANGMI_ROOT`` (default
``/``). Tests point it at a fake tree; on the device it is the real root.
"""
from __future__ import annotations

import glob
import logging
import os

log = logging.getLogger("mangmi.sysfs")


def root() -> str:
    return os.environ.get("MANGMI_ROOT", "/")


def path(p: str) -> str:
    """Map an absolute system path into the (possibly fake) root."""
    return os.path.join(root(), p.lstrip("/"))


def unroot(p: str) -> str:
    r = root().rstrip("/")
    return "/" + os.path.relpath(p, r) if r and p.startswith(r) else p


def exists(p: str) -> bool:
    return os.path.exists(path(p))


def read(p: str, default: str | None = None) -> str | None:
    try:
        with open(path(p), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return default


def read_int(p: str, default: int | None = None) -> int | None:
    v = read(p)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


# Cache of last written values: sysfs writes (especially I2C-backed LEDs)
# are comparatively expensive, so identical consecutive writes are skipped.
_last: dict[str, str] = {}


def write(p: str, value: object, *, force: bool = False) -> bool:
    s = str(value)
    full = path(p)
    if not force and _last.get(full) == s:
        return True
    try:
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(s)
        _last[full] = s
        return True
    except OSError as e:
        log.debug("write %s=%r failed: %s", p, s, e)
        _last.pop(full, None)
        return False


def forget(prefix: str = "") -> None:
    """Drop the write cache (e.g. after resume, when hardware lost state)."""
    if not prefix:
        _last.clear()
        return
    full = path(prefix)
    for k in [k for k in _last if k.startswith(full)]:
        del _last[k]


def listdir(p: str) -> list[str]:
    try:
        return sorted(os.listdir(path(p)))
    except OSError:
        return []


def glob_paths(pattern: str) -> list[str]:
    """Glob inside the root; returns *system* paths (root stripped)."""
    return sorted(unroot(m) for m in glob.glob(path(pattern)))
