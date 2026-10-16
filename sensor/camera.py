"""相機來源：Orbbec Gemini 336L（RGB + 對齊深度）或一般 webcam（無深度）。"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

import cv2
import numpy as np

from perf import PERF, timed

try:
    import pyorbbecsdk as ob
except ImportError:  # SDK 裝不起來時仍可用 webcam / replay
    ob = None


class CameraError(RuntimeError):
    pass


@dataclass
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float


@dataclass
class Frame:
    t: float
    rgb: np.ndarray  # HxWx3 uint8, RGB
    depth_mm: np.ndarray | None  # HxW 毫米（uint16 或 float32），已對齊到 rgb；0 = 無效
    intr: Intrinsics | None


SUDO_HINT = "macOS 的 UVCAssistant 會佔住 UVC 相機，請用 root 執行：sudo .venv/bin/python server.py（不要用 sudo uv run）"


ALIGN_MODES = ("sw", "hw")
DEPTH_MODES = ("default", "low")


class OrbbecCamera:
    """做法照 whosmoreareo 已實測的 OrbbecSource：
    color 1280x720 MJPG@30、depth 用 SDK 預設 Y16（336L 為 848x480）、AlignFilter 軟體 D2C。
    不先用 Context 列舉裝置：Context 活太久會佔住相機，臨時物件又會被提早回收。

    config.toml [camera]：align = "hw" 改用相機硬體 D2C（開不起來自動退回 sw）；
    depth = "low" 挑同 fps 最小的 Y16 depth（深度只在關節附近取中位數，低解析度夠用）。"""

    def __init__(self, cfg: dict | None = None, width: int = 1280, height: int = 720, fps: int = 30):
        if ob is None:
            raise CameraError("pyorbbecsdk 未安裝")
        c = (cfg or {}).get("camera", {})
        self.align_mode = c.get("align", "sw")
        self.low_depth = c.get("depth", "default") == "low"
        self.size = (width, height, fps)
        self.pipeline = None
        self.align = None
        self.intr = None

    def open(self) -> None:
        if self.align_mode == "hw":
            try:
                self._start(hw=True)
                return
            except Exception as e:
                print(f"硬體對齊（HW D2C）開啟失敗，改用軟體對齊：{e}")
        try:
            self._start(hw=False)
        except Exception as e:
            hint = f"（{SUDO_HINT}）" if _needs_sudo() else ""
            raise CameraError(f"Orbbec 開啟失敗：{e}{hint}") from e

    def _start(self, hw: bool) -> None:
        w, h, fps = self.size
        F = ob.OBFormat
        pipeline = ob.Pipeline()
        try:
            color_list = pipeline.get_stream_profile_list(ob.OBSensorType.COLOR_SENSOR)
            color_profile = _pick_profile(
                color_list, [(w, h, f, fps) for f in (F.MJPG, F.RGB, F.YUYV)] + [(w, h, F.MJPG, 0)]
            )
            if hw:
                depth_profile = self._hw_depth_profile(pipeline, color_profile, fps)
            else:
                depth_profile = self._sw_depth_profile(pipeline, fps)
            config = ob.Config()
            config.enable_stream(color_profile)
            config.enable_stream(depth_profile)
            if hw:
                config.set_align_mode(ob.OBAlignMode.HW_MODE)
            config.set_frame_aggregate_output_mode(ob.OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
            pipeline.start(config)
        except Exception:
            _stop(pipeline)
            raise
        # 硬體對齊時相機送出來的 depth 已對齊到 color，不用 AlignFilter
        self.align = None if hw else ob.AlignFilter(align_to_stream=ob.OBStreamType.COLOR_STREAM)
        self.pipeline = pipeline
        self.intr = None
        print(f"Orbbec：color {_describe(color_profile)}，depth {_describe(depth_profile)}，{'硬體' if hw else '軟體'}對齊")

    def _hw_depth_profile(self, pipeline, color_profile, fps: int):
        """硬體 D2C 可搭配的 depth：low 挑最小，否則挑最大（硬體做對齊，不吃 CPU）。"""
        profiles = pipeline.get_d2c_depth_profile_list(color_profile, ob.OBAlignMode.HW_MODE)
        p = _pick_y16(profiles, fps, low=self.low_depth)
        if p is None:
            raise CameraError(f"沒有可搭配 color 的硬體對齊 Y16 depth profile（@{fps}fps）")
        return p

    def _sw_depth_profile(self, pipeline, fps: int):
        F = ob.OBFormat
        depth_list = pipeline.get_stream_profile_list(ob.OBSensorType.DEPTH_SENSOR)
        if self.low_depth:
            p = _pick_y16(depth_list, fps, low=True)
            if p is not None:
                return p
            print(f"找不到 @{fps}fps 的 Y16 depth profile，改用預設")
        p = depth_list.get_default_video_stream_profile()
        if p.get_format() != F.Y16:
            p = _pick_profile(depth_list, [(0, 0, F.Y16, fps), (0, 0, F.Y16, 0)])
        return p

    def read(self) -> Frame | None:
        """None = 這次沒拿到完整幀；斷線丟 CameraError。"""
        try:
            with timed(PERF, "camera", "wait"):
                frames = self.pipeline.wait_for_frames(1000)
        except Exception as e:
            raise CameraError(f"Orbbec 讀取失敗：{e}") from e
        if frames is None:
            return None
        if self.align is not None:
            with timed(PERF, "camera", "align"):
                frames = self.align.process(frames)
        if not frames:
            return None
        if not hasattr(frames, "get_color_frame"):
            frames = frames.as_frame_set()
        color, depth = frames.get_color_frame(), frames.get_depth_frame()
        if not color or not depth:
            return None
        with timed(PERF, "camera", "decode"):
            rgb = _color_to_rgb(color)
        if rgb is None:
            return None
        with timed(PERF, "camera", "depth"):
            depth_mm = _depth_to_mm(depth, rgb.shape[:2])
        if self.intr is None:
            self.intr = _read_intrinsics(self.pipeline, color)
            if self.intr is None:
                return None
        return Frame(time.monotonic(), rgb, depth_mm, self.intr)

    def close(self) -> None:
        if self.pipeline is not None:
            _stop(self.pipeline)
            self.pipeline = None


class WebcamCamera:
    def __init__(self, index: int = 0):
        self.index = index
        self.cap = None

    def open(self) -> None:
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            raise CameraError(f"webcam {self.index} 開啟失敗")
        self.cap = cap

    def read(self) -> Frame | None:
        with timed(PERF, "camera", "wait"):
            ok, bgr = self.cap.read()
        if not ok:
            raise CameraError("webcam 讀取失敗")
        with timed(PERF, "camera", "decode"):
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return Frame(time.monotonic(), rgb, None, None)

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def _pick_profile(profiles, candidates):
    last = None
    for w, h, fmt, fps in candidates:
        try:
            return profiles.get_video_stream_profile(w, h, fmt, fps)
        except Exception as e:
            last = e
    raise CameraError(f"找不到符合的 stream profile：{last}")


def _video_profiles(profiles) -> list:
    out = []
    for i in range(len(profiles)):
        p = profiles[i]
        try:
            p = p.as_video_stream_profile()
        except Exception:
            pass
        out.append(p)
    return out


def _pick_y16(profiles, fps: int, low: bool):
    """Y16 且 fps 相符的 profile：low 挑 w*h 最小、否則最大。沒有回 None。"""
    cands = [p for p in _video_profiles(profiles) if p.get_format() == ob.OBFormat.Y16 and p.get_fps() == fps]
    if not cands:
        return None
    cands.sort(key=lambda p: p.get_width() * p.get_height())
    return cands[0] if low else cands[-1]


def _describe(p) -> str:
    try:
        fmt = p.get_format()
        return f"{p.get_width()}x{p.get_height()} {getattr(fmt, 'name', fmt)} @{p.get_fps()}"
    except Exception:
        return str(p)


def _depth_to_mm(depth, shape: tuple[int, int]) -> np.ndarray:
    """Y16 → mm，尺寸對齊到 color（硬體 / 軟體對齊理應同尺寸，保險起見最近鄰縮放）。
    scale = 1 時直接複製 uint16：下游只取關節附近的中位數，不必整張轉 float32。"""
    dh, dw = depth.get_height(), depth.get_width()
    raw = np.frombuffer(depth.get_data(), dtype=np.uint16)[: dh * dw].reshape(dh, dw)
    scale = float(depth.get_depth_scale())
    depth_mm = raw.copy() if scale == 1.0 else raw.astype(np.float32) * scale
    if depth_mm.shape != shape:
        depth_mm = cv2.resize(depth_mm, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return depth_mm


def _read_intrinsics(pipeline, color) -> Intrinsics | None:
    w, h = color.get_width(), color.get_height()
    candidates = []
    for get in (
        lambda: pipeline.get_camera_param().rgb_intrinsic,
        lambda: color.get_stream_profile().as_video_stream_profile().get_intrinsic(),
    ):
        try:
            candidates.append(get())
        except Exception:
            pass
    for c in candidates:
        if c.width > 0 and c.height > 0 and int(c.width) * h == int(c.height) * w:
            sx, sy = w / c.width, h / c.height
            return Intrinsics(c.fx * sx, c.fy * sy, c.cx * sx, c.cy * sy)
    return None


def _stop(pipeline) -> None:
    try:
        pipeline.stop()
    except Exception:
        pass


def _needs_sudo() -> bool:
    return sys.platform == "darwin" and os.geteuid() != 0


def _color_to_rgb(color) -> np.ndarray | None:
    w, h = color.get_width(), color.get_height()
    data = np.frombuffer(color.get_data(), dtype=np.uint8)
    fmt = color.get_format()
    if fmt == ob.OBFormat.RGB:
        return data[: h * w * 3].reshape(h, w, 3).copy()
    if fmt == ob.OBFormat.BGR:
        return cv2.cvtColor(data[: h * w * 3].reshape(h, w, 3), cv2.COLOR_BGR2RGB)
    if fmt == ob.OBFormat.MJPG:
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return None if bgr is None else cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if fmt in (ob.OBFormat.YUYV, ob.OBFormat.YUY2):
        return cv2.cvtColor(data[: h * w * 2].reshape(h, w, 2), cv2.COLOR_YUV2RGB_YUY2)
    if fmt == ob.OBFormat.UYVY:
        return cv2.cvtColor(data[: h * w * 2].reshape(h, w, 2), cv2.COLOR_YUV2RGB_UYVY)
    return None
