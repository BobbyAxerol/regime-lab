"""FP-02 item 6: actual calls/bars/callbacks/wall/CPU/RSS, measured not asserted.

Same background-sampler design as ``scripts/mem_audit.py`` (2026-09-20, the
RA-07 decay deep-dive memory audit), pulled into an importable module because
FP-02's evaluator needs it on every real engine call, not just a one-off
diagnostic script. The sampler and the measured contract are unchanged from
that precedent: 20ms-tick background thread (the engine's own Python loop
holds the GIL most of the wall time, so this does not race it), peak/base/
after-gc/residual RSS in MiB, wall seconds.
"""
from __future__ import annotations

import gc
import threading
import time
from pathlib import Path


def vm_rss_kib() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return 0


def mib(kib: int) -> float:
    return round(kib / 1024.0, 1)


class RssSampler:
    """Background peak-RSS sampler (20ms tick)."""

    def __init__(self) -> None:
        self.peak_kib = vm_rss_kib()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.peak_kib = vm_rss_kib()
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(0.02):
                rss = vm_rss_kib()
                if rss > self.peak_kib:
                    self.peak_kib = rss

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2.0)
            self._thread = None
        self.peak_kib = max(self.peak_kib, vm_rss_kib())
        return self.peak_kib


class Stage:
    """One measured call: peak RSS, wall time, and a post-gc residual reading.

    ``results[name]`` is written on exit, so a caller wraps each engine call
    it wants FP02-G-MEMORY evidence for and reads the dict back afterward --
    never estimated, never carried over from a previous call.
    """

    def __init__(self, name: str, results: dict) -> None:
        self.name = name
        self.results = results
        self.sampler = RssSampler()
        self.notes: dict = {}

    def __enter__(self) -> "Stage":
        gc.collect()
        self.base_kib = vm_rss_kib()
        self.sampler.start()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.wall_s = round(time.perf_counter() - self.t0, 3)
        peak = self.sampler.stop()
        gc.collect()
        after_kib = vm_rss_kib()
        self.results[self.name] = {
            "base_mib": mib(self.base_kib), "peak_mib": mib(peak),
            "after_gc_mib": mib(after_kib),
            "delta_mib": mib(peak - self.base_kib),
            "residual_mib": mib(after_kib - self.base_kib),
            "wall_s": self.wall_s, **self.notes,
        }
        del self.sampler
