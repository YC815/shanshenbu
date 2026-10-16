"""各階段耗時統計：每 log_s 秒印一行中位數 ms 與各執行緒實際 Hz。

  perf 5s | camera 30.0Hz wait 2.1 align 8.3 decode 1.6 depth 0.7 | pose 29.8Hz detect 7.2 total 8.5 | video 30.0Hz jpeg 2.0
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict

# 群組 → 階段，決定印出順序
LAYOUT = {
    "camera": ("wait", "align", "decode", "depth"),
    "pose": ("detect", "total"),
    "video": ("jpeg",),
}


class Perf:
    def __init__(self, log_s: float = 0, clock=time.monotonic):
        self.log_s = log_s
        self._clock = clock
        self._lock = threading.Lock()
        self._ms: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._ticks: dict[str, int] = defaultdict(int)
        self._t0 = clock()

    def add(self, group: str, stage: str, ms: float) -> None:
        if self.log_s <= 0:
            return
        with self._lock:
            self._ms[(group, stage)].append(ms)

    def tick(self, group: str) -> None:
        """一個群組完成一輪（一幀）。"""
        if self.log_s <= 0:
            return
        with self._lock:
            self._ticks[group] += 1
        self._maybe_log()

    def _maybe_log(self) -> None:
        now = self._clock()
        with self._lock:
            dt = now - self._t0
            if dt < self.log_s:
                return
            line = self._format(dt)
            self._ms.clear()
            self._ticks.clear()
            self._t0 = now
        print(line)

    def _format(self, dt: float) -> str:
        parts = [f"perf {dt:.0f}s"]
        for group, stages in LAYOUT.items():
            if not self._ticks[group]:
                continue
            s = f"{group} {self._ticks[group] / dt:.1f}Hz"
            for stage in stages:
                vals = self._ms.get((group, stage))
                if vals:
                    s += f" {stage} {statistics.median(vals):.1f}"
            parts.append(s)
        return " | ".join(parts)


class _Timer:
    def __init__(self, perf: Perf, group: str, stage: str):
        self.perf, self.group, self.stage = perf, group, stage

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.perf.add(self.group, self.stage, (time.perf_counter() - self.t) * 1000)


def timed(perf: Perf, group: str, stage: str) -> _Timer:
    return _Timer(perf, group, stage)


# 全行程共用一個；server.py 依 config 設定 log_s
PERF = Perf()


def configure(cfg: dict) -> None:
    PERF.log_s = float(cfg.get("perf", {}).get("log_s", 0))
