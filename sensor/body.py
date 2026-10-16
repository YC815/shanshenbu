"""判斷 MediaPipe 偵測到的「人」是不是真的人（擋掉樹、海報之類的誤判）。純邏輯。"""

from __future__ import annotations

from dataclasses import dataclass

CORE = ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip")


@dataclass
class Metric:
    """有深度時的真實尺寸資料。"""

    fx: float
    fy: float
    hip_z: float | None  # 髖部中心深度 m
    shoulder_z: float | None  # 肩膀中心深度 m


def looks_like_person(kp: dict, w: int, h: int, metric: Metric | None, cfg: dict) -> tuple[bool, str]:
    """回傳 (是否像人, 不像的原因)。metric 為 None（webcam）時只檢查可見度與上下順序。"""
    c = cfg["person"]
    if any(kp[n][2] < c["min_core_visibility"] for n in CORE):
        return False, "關鍵點不清楚"

    def mid(a: str, b: str) -> tuple[float, float]:
        return (kp[a][0] + kp[b][0]) / 2 * w, (kp[a][1] + kp[b][1]) / 2 * h

    sx, sy = mid("left_shoulder", "right_shoulder")
    hx, hy = mid("left_hip", "right_hip")
    nose_y = kp["nose"][1] * h
    if not (nose_y < sy < hy):
        return False, "上下順序不對"
    knees = [kp[n] for n in ("left_knee", "right_knee") if n in kp and kp[n][2] >= c["min_core_visibility"]]
    if any(k[1] * h < hy for k in knees):
        return False, "膝蓋在髖部上面"

    if metric is None:
        return True, ""
    if metric.hip_z is None:
        return False, "髖部沒有深度"
    z = metric.hip_z
    if not (c["min_distance_m"] <= z <= c["max_distance_m"]):
        return False, f"距離 {z:.1f}m 超出範圍"
    ls, rs = kp["left_shoulder"], kp["right_shoulder"]
    shoulder_m = ((ls[0] - rs[0]) * w) ** 2 + ((ls[1] - rs[1]) * h) ** 2
    shoulder_m = shoulder_m**0.5 * z / metric.fx
    if not (c["shoulder_min_m"] <= shoulder_m <= c["shoulder_max_m"]):
        return False, f"肩寬 {shoulder_m:.2f}m 不像人"
    torso_m = ((sx - hx) ** 2 + (sy - hy) ** 2) ** 0.5 * z / metric.fy
    if not (c["torso_min_m"] <= torso_m <= c["torso_max_m"]):
        return False, f"軀幹 {torso_m:.2f}m 不像人"
    if metric.shoulder_z is not None and abs(metric.shoulder_z - z) > c["max_torso_depth_diff_m"]:
        return False, "肩膀和髖部深度不連貫"
    return True, ""
