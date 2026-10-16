"""玩家鎖定：位置連續性 + 衣服顏色指紋。網頁端開局時要求鎖定（鎖當下回報的那個人），回待機就解鎖。純邏輯。"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from detector import Sample, hands_up

# 衣服指紋：部位名稱 → 正規化的 HSV 直方圖（總和 = 1）
Signature = dict[str, np.ndarray]

# 未鎖定時，回報的人這麼久沒出現就不再優先跟他
SHOWN_STALE_S = 0.3


@dataclass
class Cand:
    sample: Sample
    sig: Signature | None = None
    # 通過「像不像人」的檢查。鎖定前只採用通過的（擋樹、海報）；鎖定後側身、甩手常常不過，一律接受
    person_ok: bool = True


@dataclass
class Locked:
    u: float  # 髖部中心，影像正規化 x
    z: float | None  # 距離 m
    t: float  # 最後看到的時間
    sig: Signature | None


class PlayerLock:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.locked: Locked | None = None
        # 網頁端要的狀態（開局 True、待機 False）；只有網頁端寫，跨執行緒單純賦值
        self.want_locked = False
        self.last_match: float | None = None  # 目前鎖定的人與指紋的距離（0 = 一樣，1 = 完全不同）
        # 未鎖定時上一幀回報的人：(u, z, t)
        self._shown: tuple[float, float | None, float] | None = None

    def pick(self, t: float, cands: list[Cand]) -> Sample:
        c = self.cfg["lock"]
        if self.locked and (not self.want_locked or t - self.locked.t > c["lost_timeout_s"]):
            print("解除玩家鎖定")
            self.locked = None

        if self.locked:
            return self._follow(t, cands)
        self.last_match = None
        target = self._choose(t, cands)
        if target is None:
            return Sample(t=t)
        if self.want_locked:
            self._lock(target, t)
            print(f"鎖定玩家：距離 {target.sample.distance_m or 0:.2f}m，衣服指紋 {'有' if target.sig else '無'}")
        return target.sample

    # ------------------------------------------------------------------

    def _follow(self, t: float, cands: list[Cand]) -> Sample:
        """位置要在合理移動範圍內、衣服要像；被擋住後在別處出現，只要衣服夠像也認回來。"""
        c = self.cfg["lock"]
        L = self.locked
        allowed = c["max_jump_m"] + c["max_speed_mps"] * (t - L.t)
        best: tuple[float, float, Cand] | None = None
        for cand in cands:
            a = appearance_distance(cand.sig, L.sig)
            if a > c["appearance_max"]:
                continue  # 衣服不像：不是他
            near = _gap(cand.sample, L.u, L.z) <= allowed
            if not near and a > c["appearance_reacquire"]:
                continue  # 位置跳太遠時，只接受非常像的
            score = _gap(cand.sample, L.u, L.z) + a * c["appearance_weight"]
            if best is None or score < best[0]:
                best = (score, a, cand)
        if best is None:
            self.last_match = None
            return Sample(t=t)
        _, a, cand = best
        s = cand.sample
        self.last_match = a
        L.u, L.z, L.t = _hip_u(s), s.distance_m if s.distance_m is not None else L.z, t
        if a <= c["appearance_reacquire"]:
            L.sig = blend(L.sig, cand.sig, c["appearance_update"])
        return s

    def _choose(self, t: float, cands: list[Cand]) -> Cand | None:
        """未鎖定：舉手的人優先（他就是要開局的人）；同一群裡跟著上一幀回報的人，沒有就挑最靠畫面中央的。"""
        ok = [x for x in cands if x.person_ok]
        if not ok:
            return None
        min_vis = self.cfg["hands_up"]["min_visibility"]
        pool = [x for x in ok if hands_up(x.sample.kp, min_vis)] or ok
        shown = self._shown if self._shown and t - self._shown[2] <= SHOWN_STALE_S else None
        if shown:
            target = min(pool, key=lambda x: _gap(x.sample, shown[0], shown[1]))
        else:
            target = min(pool, key=lambda x: abs(_hip_u(x.sample) - 0.5))
        self._shown = (_hip_u(target.sample), target.sample.distance_m, t)
        return target

    def _lock(self, cand: Cand, t: float) -> None:
        s = cand.sample
        self.locked = Locked(u=_hip_u(s), z=s.distance_m, t=t, sig=cand.sig)
        self._shown = None


def appearance_distance(a: Signature | None, b: Signature | None) -> float:
    """Bhattacharyya 距離，各部位平均；沒有可比的部位回 0（只靠位置）。"""
    if not a or not b:
        return 0.0
    parts = [k for k in a if k in b]
    if not parts:
        return 0.0
    return sum(math.sqrt(max(0.0, 1.0 - float(np.sum(np.sqrt(a[k] * b[k]))))) for k in parts) / len(parts)


def blend(old: Signature | None, new: Signature | None, rate: float) -> Signature | None:
    """指紋慢慢跟著更新，適應光線變化。"""
    if not old:
        return new
    if not new:
        return old
    out = dict(old)
    for k, h in new.items():
        mixed = old[k] * (1 - rate) + h * rate if k in old else h
        out[k] = mixed / max(float(mixed.sum()), 1e-9)
    return out


def _hip_u(s: Sample) -> float:
    return (s.kp["left_hip"][0] + s.kp["right_hip"][0]) / 2


def _gap(s: Sample, u: float, z: float | None) -> float:
    # 沒深度時沿用參考距離；橫向用正規化座標 × 3m 粗估
    sz = s.distance_m if s.distance_m is not None else z
    dz = 0.0 if sz is None or z is None else sz - z
    return math.hypot((_hip_u(s) - u) * 3.0, dz)
