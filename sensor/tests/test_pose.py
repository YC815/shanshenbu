"""PoseTracker 的 GPU → CPU 退回（假 landmarker，不載模型）。"""

import time
from types import SimpleNamespace

import numpy as np
import pytest

import pose
from camera import Frame
from detector import load_config


class FakeLandmarker:
    def __init__(self, gpu, fail=False):
        self.gpu, self.fail, self.closed, self.formats = gpu, fail, False, []

    def detect_for_video(self, image, ts_ms):
        self.formats.append(image.image_format)
        if self.fail:
            raise RuntimeError("GPU boom")
        return SimpleNamespace(pose_landmarks=[])

    def close(self):
        self.closed = True


def cfg_with(delegate):
    cfg = load_config()
    cfg["pose"] = {"delegate": delegate}
    return cfg


def frame():
    return Frame(time.monotonic(), np.zeros((72, 128, 3), np.uint8), None, None)


def test_cpu_用_SRGB(monkeypatch):
    made = []
    monkeypatch.setattr(pose, "make_landmarker", lambda cfg, gpu: made.append(FakeLandmarker(gpu)) or made[-1])
    t = pose.PoseTracker(cfg_with("cpu"))
    t.process(frame())
    assert [m.gpu for m in made] == [False]
    assert made[0].formats == [pose.mp.ImageFormat.SRGB]


def test_gpu_用_SRGBA(monkeypatch):
    made = []
    monkeypatch.setattr(pose, "make_landmarker", lambda cfg, gpu: made.append(FakeLandmarker(gpu)) or made[-1])
    t = pose.PoseTracker(cfg_with("gpu"))
    t.process(frame())
    assert t.gpu and made[0].formats == [pose.mp.ImageFormat.SRGBA]


def test_gpu_建立失敗退回_cpu(monkeypatch, capsys):
    def make(cfg, gpu):
        if gpu:
            raise RuntimeError("no metal")
        return FakeLandmarker(gpu)

    monkeypatch.setattr(pose, "make_landmarker", make)
    t = pose.PoseTracker(cfg_with("gpu"))
    assert not t.gpu and not t.landmarker.gpu
    assert "改用 CPU" in capsys.readouterr().out


def test_gpu_推論失敗改用_cpu_並重跑這一幀(monkeypatch):
    made = []

    def make(cfg, gpu):
        made.append(FakeLandmarker(gpu, fail=gpu))
        return made[-1]

    monkeypatch.setattr(pose, "make_landmarker", make)
    t = pose.PoseTracker(cfg_with("gpu"))
    t.process(frame())
    gpu_lm, cpu_lm = made
    assert gpu_lm.closed and not t.gpu
    assert cpu_lm.formats == [pose.mp.ImageFormat.SRGB]  # 同一幀用 CPU 重跑
    t.process(frame())
    assert len(made) == 2  # 之後一直用 CPU，不再重建


def test_delegate_設定錯誤直接結束():
    with pytest.raises(SystemExit):
        pose.PoseTracker(cfg_with("tpu"))
