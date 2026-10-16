"""OrbbecCamera 的 profile 選擇與硬體對齊退回邏輯（假 SDK，不需要相機）。"""

from enum import Enum
from types import SimpleNamespace

import pytest

import camera
from sources import make_camera


class F(Enum):
    MJPG = 1
    RGB = 2
    YUYV = 3
    Y16 = 4
    Y8 = 5


class P:
    def __init__(self, w, h, fmt=F.Y16, fps=30):
        self.w, self.h, self.fmt, self.fps = w, h, fmt, fps

    def get_width(self):
        return self.w

    def get_height(self):
        return self.h

    def get_format(self):
        return self.fmt

    def get_fps(self):
        return self.fps

    def as_video_stream_profile(self):
        return self


class PList(list):
    def get_video_stream_profile(self, w, h, fmt, fps):
        for p in self:
            if (w in (0, p.w)) and (h in (0, p.h)) and p.fmt == fmt and fps in (0, p.fps):
                return p
        raise RuntimeError("no profile")

    def get_default_video_stream_profile(self):
        return self[0]


COLOR = PList([P(1280, 720, F.MJPG)])
DEPTH = PList([P(848, 480), P(1280, 800), P(424, 240), P(424, 240, fps=15), P(640, 400, F.Y8)])


class FakeSdk:
    def __init__(self, d2c=None, start_fails_with_hw=False):
        self.d2c = PList([P(848, 480), P(424, 240)]) if d2c is None else d2c
        self.start_fails_with_hw = start_fails_with_hw
        self.started = []  # 每次成功 start 的 (depth profile, align mode)
        sdk = self
        self.OBFormat = F
        self.OBSensorType = SimpleNamespace(COLOR_SENSOR="color", DEPTH_SENSOR="depth")
        self.OBAlignMode = SimpleNamespace(HW_MODE="hw")
        self.OBStreamType = SimpleNamespace(COLOR_STREAM="color")
        self.OBFrameAggregateOutputMode = SimpleNamespace(FULL_FRAME_REQUIRE="full")

        class Config:
            def __init__(self):
                self.streams, self.align = [], None

            def enable_stream(self, p):
                self.streams.append(p)

            def set_align_mode(self, m):
                self.align = m

            def set_frame_aggregate_output_mode(self, m):
                pass

        class Pipeline:
            def get_stream_profile_list(self, sensor):
                return COLOR if sensor == "color" else DEPTH

            def get_d2c_depth_profile_list(self, color, mode):
                return sdk.d2c

            def start(self, config):
                if config.align == "hw" and sdk.start_fails_with_hw:
                    raise RuntimeError("hw start failed")
                sdk.started.append((config.streams[1], config.align))

            def stop(self):
                pass

        self.Config = Config
        self.Pipeline = Pipeline
        self.AlignFilter = lambda align_to_stream: "align-filter"


def open_cam(monkeypatch, sdk, align="sw", depth="default"):
    monkeypatch.setattr(camera, "ob", sdk)
    cam = make_camera(None, {"camera": {"align": align, "depth": depth}})()
    cam.open()
    return cam


def test_sw_default_用_SDK_預設_depth(monkeypatch):
    sdk = FakeSdk()
    cam = open_cam(monkeypatch, sdk)
    assert sdk.started == [(DEPTH[0], None)]
    assert cam.align == "align-filter"


def test_sw_low_挑同_fps_最小的_Y16(monkeypatch):
    sdk = FakeSdk()
    open_cam(monkeypatch, sdk, depth="low")
    (p, mode), = sdk.started
    assert (p.w, p.h, p.fps, p.fmt, mode) == (424, 240, 30, F.Y16, None)


def test_hw_用_d2c_清單且不建_AlignFilter(monkeypatch):
    sdk = FakeSdk()
    cam = open_cam(monkeypatch, sdk, align="hw")
    (p, mode), = sdk.started
    assert ((p.w, p.h), mode) == ((848, 480), "hw")  # default 挑最大
    assert cam.align is None


def test_hw_low_挑最小(monkeypatch):
    sdk = FakeSdk()
    open_cam(monkeypatch, sdk, align="hw", depth="low")
    (p, mode), = sdk.started
    assert ((p.w, p.h), mode) == ((424, 240), "hw")


@pytest.mark.parametrize("sdk", [FakeSdk(d2c=PList()), FakeSdk(start_fails_with_hw=True)], ids=["清單空", "start失敗"])
def test_hw_失敗退回_sw(monkeypatch, sdk, capsys):
    cam = open_cam(monkeypatch, sdk, align="hw")
    assert sdk.started == [(DEPTH[0], None)]
    assert cam.align == "align-filter"
    assert "改用軟體對齊" in capsys.readouterr().out


def test_設定值錯誤直接結束():
    with pytest.raises(SystemExit):
        make_camera(None, {"camera": {"align": "gpu"}})


def test_webcam_不看_camera_設定():
    cam = make_camera(0, {"camera": {"align": "bogus"}})()
    assert isinstance(cam, camera.WebcamCamera)
