# SPDX-License-Identifier: GPL-2.0-or-later
"""CPU (2 clusters) and GPU (Adreno 610 devfreq) performance profiles."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import sysfs

log = logging.getLogger("mangmi.perf")

CPUFREQ = "/sys/devices/system/cpu/cpufreq"
DEVFREQ = "/sys/class/devfreq"


@dataclass
class Domain:
    path: str
    freqs: list[int]       # ascending, kHz for CPU / Hz for GPU
    kind: str              # "little" | "big" | "gpu"
    governors: list[str]

    @property
    def lo(self) -> int:
        return self.freqs[0]

    @property
    def hi(self) -> int:
        return self.freqs[-1]

    def at_most(self, frac: float) -> int:
        cap = self.hi * frac
        return max([f for f in self.freqs if f <= cap] or [self.lo])

    def at_least(self, frac: float) -> int:
        floor = self.hi * frac
        return min([f for f in self.freqs if f >= floor] or [self.hi])


def _freq_list(raw: str | None) -> list[int]:
    out = []
    for tok in (raw or "").split():
        try:
            out.append(int(tok))
        except ValueError:
            pass
    return sorted(set(out))


def cpu_domains() -> list[Domain]:
    pols = []
    for name in sysfs.listdir(CPUFREQ):
        if not name.startswith("policy"):
            continue
        p = f"{CPUFREQ}/{name}"
        freqs = _freq_list(sysfs.read(f"{p}/scaling_available_frequencies"))
        if not freqs:
            lo, hi = sysfs.read_int(f"{p}/cpuinfo_min_freq"), sysfs.read_int(f"{p}/cpuinfo_max_freq")
            freqs = [f for f in (lo, hi) if f]
        if freqs:
            govs = (sysfs.read(f"{p}/scaling_available_governors") or "").split()
            pols.append(Domain(p, freqs, "little", govs))
    if len(pols) > 1:
        top = max(d.hi for d in pols)
        for d in pols:
            d.kind = "big" if d.hi == top and d.path != pols[0].path else "little"
    return pols


def gpu_domain() -> Domain | None:
    for name in sysfs.listdir(DEVFREQ):
        if "gpu" not in name:
            continue
        p = f"{DEVFREQ}/{name}"
        freqs = _freq_list(sysfs.read(f"{p}/available_frequencies"))
        if freqs:
            govs = (sysfs.read(f"{p}/available_governors") or "").split()
            return Domain(p, freqs, "gpu", govs)
    return None


# profile -> settings. Fractions are relative to the domain's top frequency.
PROFILES = {
    "powersave":   {"cpu_gov": "schedutil", "cpu_max": 0.70, "cpu_min": None,
                    "gpu_gov": "simple_ondemand", "gpu_max": 0.60, "gpu_min": None},
    "balanced":    {"cpu_gov": "schedutil", "cpu_max": 1.00, "cpu_min": None,
                    "gpu_gov": "simple_ondemand", "gpu_max": 1.00, "gpu_min": None},
    "performance": {"cpu_gov": "schedutil", "cpu_max": 1.00, "cpu_min": 0.50,
                    "gpu_gov": "simple_ondemand", "gpu_max": 1.00, "gpu_min": 0.55},
    "max":         {"cpu_gov": "performance", "cpu_max": 1.00, "cpu_min": None,
                    "gpu_gov": "performance", "gpu_max": 1.00, "gpu_min": None},
}


def _pick_gov(dom: Domain, want: str) -> str | None:
    if not dom.governors or want in dom.governors:
        return want
    for alt in ("schedutil", "simple_ondemand", "ondemand"):
        if alt in dom.governors:
            return alt
    return None


def apply(profile: str) -> dict:
    cfg = PROFILES[profile]
    done: dict = {"profile": profile}
    for dom in cpu_domains():
        gov = _pick_gov(dom, cfg["cpu_gov"])
        if gov:
            sysfs.write(f"{dom.path}/scaling_governor", gov, force=True)
        mx = dom.at_most(cfg["cpu_max"])
        mn = dom.at_least(cfg["cpu_min"]) if cfg["cpu_min"] else dom.lo
        mn = min(mn, mx)
        # widen first so the kernel never sees min > max
        sysfs.write(f"{dom.path}/scaling_max_freq", dom.hi, force=True)
        sysfs.write(f"{dom.path}/scaling_min_freq", mn, force=True)
        sysfs.write(f"{dom.path}/scaling_max_freq", mx, force=True)
        done[dom.kind] = {"governor": gov, "min_khz": mn, "max_khz": mx}
    gpu = gpu_domain()
    if gpu:
        gov = _pick_gov(gpu, cfg["gpu_gov"])
        if gov:
            sysfs.write(f"{gpu.path}/governor", gov, force=True)
        mx = gpu.at_most(cfg["gpu_max"])
        mn = gpu.at_least(cfg["gpu_min"]) if cfg["gpu_min"] else gpu.lo
        mn = min(mn, mx)
        sysfs.write(f"{gpu.path}/min_freq", gpu.lo, force=True)
        sysfs.write(f"{gpu.path}/max_freq", mx, force=True)
        sysfs.write(f"{gpu.path}/min_freq", mn, force=True)
        done["gpu"] = {"governor": gov, "min_hz": mn, "max_hz": mx}
    return done


def snapshot() -> dict:
    out = {}
    for dom in cpu_domains():
        out[dom.kind] = {
            "governor": sysfs.read(f"{dom.path}/scaling_governor"),
            "cur_khz": sysfs.read_int(f"{dom.path}/scaling_cur_freq"),
            "max_khz": sysfs.read_int(f"{dom.path}/scaling_max_freq"),
        }
    gpu = gpu_domain()
    if gpu:
        out["gpu"] = {
            "governor": sysfs.read(f"{gpu.path}/governor"),
            "cur_hz": sysfs.read_int(f"{gpu.path}/cur_freq"),
            "max_hz": sysfs.read_int(f"{gpu.path}/max_freq"),
        }
    return out
