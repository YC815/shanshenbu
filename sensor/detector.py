"""動作判定：關鍵點時間序列 → 協定狀態。純邏輯，不碰 I/O。"""

from __future__ import annotations

import math
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.toml")

# 關鍵點：影像正規化座標 (x, y, visibility)，x 往影像右、y 往下
Keypoints = dict[str, tuple[float, float, float]]

ARM_POINTS = ("left_elbow", "right_elbow", "left_wrist", "right_wrist")
# 閃身步三個軸（玩家視角）：(數值變大的事件, 數值變小的事件)
STEP_AXES = (("step_right", "step_left"), ("step_up", "step_down"), ("step_back", "step_forward"))


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass
class Sample:
    t: float
    kp: Keypoints | None = None
    # 相機座標系：+x = 影像右方（= 玩家的左手邊）
    hip_x_m: float | None = None
    distance_m: float | None = None
    # 相機座標系：+y = 影像下方
    hip_y_m: float | None = None

    def to_dict(self) -> dict:
        return {
            "t": self.t,
            "kp": {k: list(v) for k, v in self.kp.items()} if self.kp else None,
            "hip_x_m": self.hip_x_m,
            "distance_m": self.distance_m,
            "hip_y_m": self.hip_y_m,
        }

    @staticmethod
    def from_dict(d: dict) -> "Sample":
        kp = d.get("kp")
        return Sample(
            t=d["t"],
            kp={k: tuple(v) for k, v in kp.items()} if kp else None,
            hip_x_m=d.get("hip_x_m"),
            distance_m=d.get("distance_m"),
            hip_y_m=d.get("hip_y_m"),
        )


@dataclass
class Detector:
    cfg: dict = field(default_factory=load_config)
    _hip_hist: deque = field(default_factory=deque)  # (t, (x 玩家右為正, y 上為正, z 遠為正))
    _arm_prev: tuple[float, dict[str, tuple[float, float]]] | None = None
    _speed_hist: deque = field(default_factory=deque)  # (t, speed)
    _last_step_t: float = -math.inf
    _last_distance: float | None = None
    _last_present_t: float = -math.inf
    _last_state: dict | None = None

    def update(self, s: Sample) -> dict:
        present = self._present(s)
        if s.distance_m is not None:
            self._last_distance = s.distance_m
        hold_s = self.cfg["presence"]["hold_s"]
        if not present:
            # 掉幾幀（甩手、側身時 MediaPipe 常漏）不算消失：沿用上一幀，動作歷史也不清
            if self._last_state is not None and s.t - self._last_present_t <= hold_s:
                return {**self._last_state, "events": []}
            self._clear()
            return {
                "status": "ok",
                "present": False,
                "distance_m": self._last_distance,
                "x_m": None,
                "y_m": None,
                "events": [],
                "shaking": False,
                "hands_up": False,
            }

        if s.t - self._last_present_t > hold_s:
            self._clear()  # 消失太久後回來：可能換了人，舊歷史不能拿來算位移
        self._last_present_t = s.t
        x_player = -s.hip_x_m if s.hip_x_m is not None else None
        y_up = -s.hip_y_m if s.hip_y_m is not None else None
        events = self._step(s.t, (x_player, y_up, s.distance_m))
        self._last_state = {
            "status": "ok",
            "present": True,
            "distance_m": _round(self._last_distance),
            "x_m": _round(x_player),
            "y_m": _round(y_up),
            "events": events,
            "shaking": self._shaking(s.t, s.kp),
            "hands_up": hands_up(s.kp, self.cfg["hands_up"]["min_visibility"]),
        }
        return dict(self._last_state)

    def _clear(self) -> None:
        self._hip_hist.clear()
        self._speed_hist.clear()
        self._arm_prev = None
        self._last_state = None

    def _present(self, s: Sample) -> bool:
        if not s.kp:
            return False
        vis = (s.kp["left_hip"][2] + s.kp["right_hip"][2]) / 2
        return vis >= self.cfg["presence"]["min_hip_visibility"]

    def _step(self, t: float, pos: tuple[float | None, float | None, float | None]) -> list[str]:
        """上下左右前後任一軸，window_s 內位移 >= min_shift_m 就算一次閃身步；取位移最大的軸。"""
        if all(v is None for v in pos):
            return []
        c = self.cfg["step"]
        self._hip_hist.append((t, pos))
        while self._hip_hist and t - self._hip_hist[0][0] > c["window_s"]:
            self._hip_hist.popleft()
        if t - self._last_step_t < c["cooldown_s"]:
            return []
        best: tuple[float, str] | None = None
        for i, (inc_event, dec_event) in enumerate(STEP_AXES):
            cur = pos[i]
            vals = [p[i] for _, p in self._hip_hist if p[i] is not None]
            if cur is None or not vals:
                continue
            for shift, event in ((cur - min(vals), inc_event), (max(vals) - cur, dec_event)):
                if shift >= c["min_shift_m"] and (best is None or shift > best[0]):
                    best = (shift, event)
        if best is None:
            return []
        self._last_step_t = t
        self._hip_hist.clear()
        self._hip_hist.append((t, pos))
        return [best[1]]

    def _shaking(self, t: float, kp: Keypoints) -> bool:
        c = self.cfg["shake"]
        ls, rs = kp["left_shoulder"], kp["right_shoulder"]
        shoulder_w = math.hypot(ls[0] - rs[0], ls[1] - rs[1])
        if shoulder_w < 1e-3:
            return False
        cx, cy = (ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2
        # 相對肩膀中心，扣掉整個人橫移（閃身步）造成的速度
        arms = {n: ((kp[n][0] - cx) / shoulder_w, (kp[n][1] - cy) / shoulder_w) for n in ARM_POINTS}

        prev, self._arm_prev = self._arm_prev, (t, arms)
        if prev is not None and t > prev[0]:
            dt = t - prev[0]
            speed = sum(math.hypot(arms[n][0] - prev[1][n][0], arms[n][1] - prev[1][n][1]) for n in ARM_POINTS)
            self._speed_hist.append((t, speed / len(ARM_POINTS) / dt))
        while self._speed_hist and t - self._speed_hist[0][0] > c["window_s"]:
            self._speed_hist.popleft()
        if not self._speed_hist:
            return False
        # 中位數：單次大動作（例如手一次放下）的尖峰不會撐高結果，要持續晃才算
        speeds = sorted(v for _, v in self._speed_hist)
        return speeds[len(speeds) // 2] > c["min_speed"]


def hands_up(kp: Keypoints | None, min_vis: float) -> bool:
    """雙手腕都比鼻子高（開局手勢）。畫面上請玩家「舉過頭頂」，留餘裕。"""
    if not kp:
        return False
    nose = kp["nose"]
    return all(w[2] >= min_vis and w[1] < nose[1] for w in (kp["left_wrist"], kp["right_wrist"]))


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 3) + 0.0
