"""Hardware/performance metrics for telemetry: CPU, memory, SoC temperature,
iGPU frequency, and real NPU utilization — all read from /proc and /sys (which
Docker mounts read-only), so no privileged container is needed.

Notes for the NUC's integrated SoC (Arrow Lake):
  * CPU, iGPU and NPU are one chip — there is a single package temperature
    (`soc_temp_c`), not separate GPU/NPU thermal sensors.
  * System RAM is the shared memory pool for the iGPU and NPU, so `mem_*` covers
    "GPU memory" too.
  * The iGPU (xe driver) exposes frequency but no busy-% counter in sysfs;
    `gpu_freq_mhz`/`gpu_freq_pct` are the activity proxy. True per-engine GPU %
    needs intel_gpu_top (PMU access) — not enabled here.
  * The NPU exposes a cumulative busy-time counter, so `npu_busy_pct` is real.
"""
from __future__ import annotations

import glob
import logging
import os
import time

log = logging.getLogger("sysmon")


def _read_int(path: str):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:  # noqa: BLE001
        return None


def _find_npu_dir():
    for p in glob.glob("/sys/devices/pci*/*/npu_busy_time_us"):
        return os.path.dirname(p)
    return None


def _find_gpu_freq_dir():
    # xe driver: <pci>/tile0/gt0/freq0/act_freq  (gt0 = render/compute)
    hits = sorted(glob.glob("/sys/devices/pci*/*/tile*/gt0/freq0/act_freq"))
    return os.path.dirname(hits[0]) if hits else None


class SysMon:
    def __init__(self):
        try:
            import psutil
            self._psutil = psutil
            psutil.cpu_percent(interval=None)  # prime the delta
        except Exception:  # noqa: BLE001
            self._psutil = None
            log.warning("psutil unavailable; CPU/mem/temp metrics disabled")
        self.npu_dir = _find_npu_dir()
        self.gpu_freq_dir = _find_gpu_freq_dir()
        self._npu_prev = None  # (busy_us, monotonic_s)

    def read(self) -> dict:
        m: dict = {}
        ps = self._psutil
        if ps is not None:
            try:
                m["cpu_percent"] = round(ps.cpu_percent(interval=None), 1)
            except Exception:  # noqa: BLE001
                pass
            try:
                vm = ps.virtual_memory()
                m["mem_used_mb"] = round(vm.used / 1e6)
                m["mem_total_mb"] = round(vm.total / 1e6)
                m["mem_percent"] = vm.percent
            except Exception:  # noqa: BLE001
                pass
            t = self._package_temp(ps)
            if t is not None:
                m["soc_temp_c"] = t

        # iGPU frequency (activity proxy)
        if self.gpu_freq_dir:
            act = _read_int(self.gpu_freq_dir + "/act_freq")
            mx = _read_int(self.gpu_freq_dir + "/max_freq") or _read_int(self.gpu_freq_dir + "/rp0_freq")
            if act is not None:
                m["gpu_freq_mhz"] = act
                if mx:
                    m["gpu_freq_pct"] = round(100.0 * act / mx, 1)

        # NPU: real utilization from the cumulative busy-time counter
        if self.npu_dir:
            cur = _read_int(self.npu_dir + "/npu_current_frequency_mhz")
            mem = _read_int(self.npu_dir + "/npu_memory_utilization")
            busy = _read_int(self.npu_dir + "/npu_busy_time_us")
            if cur is not None:
                m["npu_freq_mhz"] = cur
            if mem is not None:
                m["npu_mem_mb"] = round(mem / 1e6)
            if busy is not None:
                now = time.monotonic()
                if self._npu_prev:
                    pb, pt = self._npu_prev
                    dt_us = (now - pt) * 1e6
                    if dt_us > 0:
                        pct = 100.0 * (busy - pb) / dt_us
                        m["npu_busy_pct"] = round(max(0.0, min(100.0, pct)), 1)
                self._npu_prev = (busy, now)
        return m

    def _package_temp(self, ps):
        try:
            temps = ps.sensors_temperatures()
        except Exception:  # noqa: BLE001
            temps = {}
        # Prefer the CPU package sensor.
        for name in ("coretemp", "k10temp"):
            for e in temps.get(name, []):
                if "package" in (e.label or "").lower():
                    return round(e.current, 1)
        # Fallback: direct sysfs scan for a 'Package' label.
        for lbl in glob.glob("/sys/class/hwmon/hwmon*/temp*_label"):
            try:
                if "package" in open(lbl).read().lower():
                    v = _read_int(lbl.replace("_label", "_input"))
                    if v:
                        return round(v / 1000.0, 1)
            except Exception:  # noqa: BLE001
                pass
        # Last resort: first available sensor.
        for name in ("coretemp", "acpitz"):
            for e in temps.get(name, []):
                return round(e.current, 1)
        return None
