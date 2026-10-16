"""MediaPipe PoseLandmarker：Frame → Sample（關鍵點 + 髖部 3D 位置）。"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path

import mediapipe as mp
import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from body import Metric, looks_like_person
from camera import Frame
from detector import Sample
from lock import Cand, PlayerLock, Signature
from perf import PERF, timed

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
MODEL_PATH = Path(__file__).with_name("models") / "pose_landmarker_lite.task"

LANDMARKS = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
}
# 衣服指紋的部位：(上緣兩點, 下緣兩點)
CLOTHING_PARTS = {
    "torso": (("left_shoulder", "right_shoulder"), ("left_hip", "right_hip")),
    "legs": (("left_hip", "right_hip"), ("left_knee", "right_knee")),
}


def ensure_model(path: Path = MODEL_PATH) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"下載模型 → {path}")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.rename(path)
    return path


def make_landmarker(cfg: dict, gpu: bool):
    kw = {"delegate": BaseOptions.Delegate.GPU} if gpu else {}
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_model()), **kw),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=cfg["lock"]["max_people"],
    )
    return vision.PoseLandmarker.create_from_options(options)


def _mp_image(rgb: np.ndarray, gpu: bool) -> mp.Image:
    # GPU delegate 只吃 4 通道
    if gpu:
        return mp.Image(image_format=mp.ImageFormat.SRGBA, data=cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA))
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


class PoseTracker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        delegate = cfg.get("pose", {}).get("delegate", "cpu")
        if delegate not in ("cpu", "gpu"):
            raise SystemExit(f"config.toml [pose] delegate 只能是 cpu 或 gpu，收到 {delegate!r}")
        self.gpu = delegate == "gpu"
        self.landmarker = self._create()
        self._last_ts_ms = -1
        self.lock = PlayerLock(cfg)
        self._reject_log_t = 0.0

    def _create(self):
        if self.gpu:
            try:
                return make_landmarker(self.cfg, gpu=True)
            except Exception as e:
                print(f"MediaPipe GPU delegate 建立失敗，改用 CPU：{e}")
                self.gpu = False
        return make_landmarker(self.cfg, gpu=False)

    def _detect(self, rgb: np.ndarray, ts_ms: int):
        """GPU 推論出錯就永久改用 CPU，並用 CPU 重跑這一幀。"""
        if self.gpu:
            try:
                return self.landmarker.detect_for_video(_mp_image(rgb, gpu=True), ts_ms)
            except Exception as e:
                print(f"MediaPipe GPU 推論失敗，改用 CPU：{e}")
                self._fallback_to_cpu()
        return self.landmarker.detect_for_video(_mp_image(rgb, gpu=False), ts_ms)

    def _fallback_to_cpu(self) -> None:
        self.gpu = False
        try:
            self.landmarker.close()
        except Exception:
            pass
        self.landmarker = make_landmarker(self.cfg, gpu=False)

    def process(self, frame: Frame) -> Sample:
        with timed(PERF, "pose", "total"):
            sample = self._process(frame)
        PERF.tick("pose")
        return sample

    def _process(self, frame: Frame) -> Sample:
        ts_ms = max(int(frame.t * 1000), self._last_ts_ms + 1)
        self._last_ts_ms = ts_ms
        with timed(PERF, "pose", "detect"):
            result = self._detect(frame.rgb, ts_ms)
        min_vis = self.cfg["presence"]["min_hip_visibility"]
        h, w = frame.rgb.shape[:2]
        cands, rejected = [], []
        for lm in result.pose_landmarks:
            sample = self._measure(frame, lm)
            if (sample.kp["left_hip"][2] + sample.kp["right_hip"][2]) / 2 < min_vis:
                continue
            ok, why = looks_like_person(sample.kp, w, h, self._metric(frame, sample), self.cfg)
            if not ok:
                rejected.append(why)
            cands.append(Cand(sample, clothing_signature(frame.rgb, sample.kp), person_ok=ok))
        if rejected and frame.t - self._reject_log_t > 2.0:
            self._reject_log_t = frame.t
            print(f"不像人（鎖定前不採用）：{'、'.join(rejected)}")
        return self.lock.pick(frame.t, cands)

    def _metric(self, frame: Frame, sample: Sample) -> Metric | None:
        if frame.depth_mm is None or frame.intr is None:
            return None
        h, w = frame.rgb.shape[:2]
        kp = sample.kp
        su = (kp["left_shoulder"][0] + kp["right_shoulder"][0]) / 2 * w
        sv = (kp["left_shoulder"][1] + kp["right_shoulder"][1]) / 2 * h
        shoulder_z = _patch_median_m(frame.depth_mm, su, sv, self.cfg["depth"]["hip_patch_px"])
        return Metric(frame.intr.fx, frame.intr.fy, sample.distance_m, shoulder_z)

    def _measure(self, frame: Frame, lm) -> Sample:
        kp = {name: (lm[i].x, lm[i].y, lm[i].visibility or 0.0) for name, i in LANDMARKS.items()}
        h, w = frame.rgb.shape[:2]
        hip_u = (kp["left_hip"][0] + kp["right_hip"][0]) / 2 * w
        hip_v = (kp["left_hip"][1] + kp["right_hip"][1]) / 2 * h

        if frame.depth_mm is not None and frame.intr is not None:
            z = _patch_median_m(frame.depth_mm, hip_u, hip_v, self.cfg["depth"]["hip_patch_px"])
            if z is None:
                return Sample(t=frame.t, kp=kp)
            hip_x = (hip_u - frame.intr.cx) * z / frame.intr.fx
            hip_y = (hip_v - frame.intr.cy) * z / frame.intr.fy
            return Sample(t=frame.t, kp=kp, hip_x_m=hip_x, distance_m=z, hip_y_m=hip_y)

        # 無深度：用肩寬像素估距離（粗略）
        c = self.cfg["webcam"]
        f_px = (w / 2) / math.tan(math.radians(c["hfov_deg"] / 2))
        ls, rs = kp["left_shoulder"], kp["right_shoulder"]
        shoulder_px = math.hypot((ls[0] - rs[0]) * w, (ls[1] - rs[1]) * h)
        if shoulder_px < 1:
            return Sample(t=frame.t, kp=kp)
        z = c["shoulder_width_m"] * f_px / shoulder_px
        return Sample(
            t=frame.t, kp=kp, hip_x_m=(hip_u - w / 2) * z / f_px, distance_m=z, hip_y_m=(hip_v - h / 2) * z / f_px
        )

    def close(self) -> None:
        self.landmarker.close()


def clothing_signature(rgb: np.ndarray, kp: dict, min_vis: float = 0.5) -> Signature | None:
    """上衣、褲子區域的 HSV 直方圖（12×4×4）。關鍵點看不清楚的部位略過。"""
    h, w = rgb.shape[:2]
    sig: Signature = {}
    for part, (top, bottom) in CLOTHING_PARTS.items():
        pts = [kp[n] for n in top + bottom]
        if any(p[2] < min_vis for p in pts):
            continue
        xs = [p[0] * w for p in pts]
        x0, x1 = min(xs), max(xs)
        y0 = min(kp[n][1] for n in top) * h
        y1 = max(kp[n][1] for n in bottom) * h
        # 往內縮，避免框到背景
        dx, dy = (x1 - x0) * 0.2, (y1 - y0) * 0.1
        x0, x1, y0, y1 = int(max(0, x0 + dx)), int(min(w, x1 - dx)), int(max(0, y0 + dy)), int(min(h, y1 - dy))
        if x1 - x0 < 6 or y1 - y0 < 6:
            continue
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb[y0:y1:2, x0:x1:2]), cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
        total = float(hist.sum())
        if total > 0:
            sig[part] = hist / total
    return sig or None


def _patch_median_m(depth_mm: np.ndarray, u: float, v: float, r: int) -> float | None:
    h, w = depth_mm.shape
    ui, vi = int(round(u)), int(round(v))
    patch = depth_mm[max(vi - r, 0) : min(vi + r + 1, h), max(ui - r, 0) : min(ui + r + 1, w)]
    valid = patch[patch > 0]
    if valid.size == 0:
        return None
    return float(np.median(valid)) / 1000.0
