# SPDX-License-Identifier: GPL-2.0-or-later
"""Interrupt placement for SM6115 (from ROCKNIX quirks/platforms/SM6115).

Keeps latency-sensitive and bulky interrupts off the big A73 cores (4-7), so
emulator threads pinned there are never interrupted by storage/USB traffic.
GIC SPI numbers are used, which are stable across kernels.
"""
from __future__ import annotations

import logging
import re

from . import sysfs

log = logging.getLogger("mangmi.irq")

# GIC SPI -> CPU list
SM6115_AFFINITY = {
    177: "3",     # GPU
    186: "3",     # MDSS (display)
    348: "1-2",   # eMMC
    350: "1-2",   # SD card
    255: "1-2",   # USB
    327: "2",     # gamepad UART
    194: "1",
    421: "1",     # BWMon
}

_LINE = re.compile(r"^\s*(\d+):(.*)$")


def gic_map(interrupts: str) -> dict[int, list[int]]:
    """Parse /proc/interrupts -> {GIC SPI number: [linux irq, ...]}"""
    out: dict[int, list[int]] = {}
    for line in interrupts.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        toks = m.group(2).split()
        for i, tok in enumerate(toks[:-1]):
            if tok.startswith("GICv3") and toks[i + 1].isdigit():
                hw = int(toks[i + 1])
                if hw >= 32:
                    out.setdefault(hw - 32, []).append(int(m.group(1)))
                break
    return out


def apply(table: dict[int, str] = SM6115_AFFINITY) -> int:
    raw = sysfs.read("/proc/interrupts") or ""
    mapping = gic_map(raw)
    n = 0
    for spi, cpus in table.items():
        for irq in mapping.get(spi, []):
            if sysfs.write(f"/proc/irq/{irq}/smp_affinity_list", cpus, force=True):
                n += 1
    log.info("irq affinity: %d interrupts placed", n)
    return n
