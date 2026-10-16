"""Sample 來源：相機（含斷線重試）或 JSONL 回放。產出 Sample，None 代表相機未連線。"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from camera import ALIGN_MODES, DEPTH_MODES, CameraError, Frame, OrbbecCamera, WebcamCamera
from detector import Sample
from perf import PERF


def make_camera(webcam: int | None, cfg: dict) -> Callable:
    if webcam is not None:
        return lambda: WebcamCamera(webcam)
    c = cfg.get("camera", {})
    if c.get("align", "sw") not in ALIGN_MODES or c.get("depth", "default") not in DEPTH_MODES:
        raise SystemExit(f"config.toml [camera] 設定錯誤：align 只能是 {ALIGN_MODES}、depth 只能是 {DEPTH_MODES}")
    return lambda: OrbbecCamera(cfg)


class CameraThread:
    """獨立執行緒一直讀相機、只留最新一幀。

    不能在消費端慢慢讀：處理一幀超過 33ms 時 Orbbec SDK 的 10 格佇列會塞滿，
    之後拿到的都是最舊的幀，延遲固定多 ~330ms。
    """

    def __init__(self, make_cam: Callable, retry_s: float):
        self.make_cam = make_cam
        self.retry_s = retry_s
        self.connected = False
        self._seq = 0
        self._frame: Frame | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def latest(self) -> tuple[int, Frame | None]:
        with self._lock:
            return self._seq, self._frame

    async def next_frame(self, after_seq: int) -> tuple[int, Frame | None]:
        """等到比 after_seq 新的幀；相機未連線時每 0.5s 回一次 (seq, None)。"""
        waited = 0.0
        while True:
            seq, frame = self.latest()
            if self.connected and seq > after_seq:
                return seq, frame
            if not self.connected and waited >= 0.5:
                return after_seq, None
            await asyncio.sleep(0.003)
            waited += 0.003

    def _run(self) -> None:
        cam = None
        while not self._stop.is_set():
            if cam is None:
                try:
                    cam = self.make_cam()
                    cam.open()
                    print("相機已連線")
                    self.connected = True
                except CameraError as e:
                    print(f"相機未連線：{e}（{self.retry_s}s 後重試）")
                    cam = None
                    self._stop.wait(self.retry_s)
                    continue
            try:
                frame = cam.read()
            except CameraError as e:
                print(f"相機斷線：{e}")
                self.connected = False
                cam.close()
                cam = None
                continue
            if frame is None:
                continue
            PERF.tick("camera")
            with self._lock:
                self._seq += 1
                self._frame = frame
        if cam is not None:
            cam.close()


async def camera_samples(cam: CameraThread, cfg: dict, tracker=None) -> AsyncIterator[Sample | None]:
    """對 cam 的最新幀做姿勢辨識；處理不及的幀直接跳過。None = 相機未連線。"""
    from pose import PoseTracker  # 延後載入：replay 模式不需要 mediapipe 模型

    tracker = tracker or PoseTracker(cfg)
    seq = 0
    try:
        while True:
            seq, frame = await cam.next_frame(seq)
            if frame is None:
                yield None
                continue
            yield await asyncio.to_thread(tracker.process, frame)
    finally:
        tracker.close()


async def replay_samples(path: Path, loop: bool = True) -> AsyncIterator[Sample]:
    samples = [Sample.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
    if not samples:
        raise SystemExit(f"{path} 沒有資料")
    t0_rec = samples[0].t
    while True:
        t0 = time.monotonic()
        for s in samples:
            delay = (s.t - t0_rec) - (time.monotonic() - t0)
            if delay > 0:
                await asyncio.sleep(delay)
            yield Sample(t=t0 + (s.t - t0_rec), kp=s.kp, hip_x_m=s.hip_x_m, distance_m=s.distance_m, hip_y_m=s.hip_y_m)
        if not loop:
            return
        # 循環接縫停一下再送空幀：間隔超過 detector 的 hold_s 它才會清歷史，避免頭尾位置差變成假事件
        await asyncio.sleep(1.0)
        yield Sample(t=time.monotonic())
