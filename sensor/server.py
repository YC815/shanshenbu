"""WebSocket 伺服器：每幀推送協定 JSON 給網頁端。

  uv run python server.py              # Orbbec Gemini 336L
  uv run python server.py --webcam 0   # 一般攝影機（距離用肩寬估）
  uv run python server.py --replay rec.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json

import cv2
from pathlib import Path

from websockets.asyncio.server import broadcast, serve

from detector import Detector, load_config
from perf import PERF, configure as configure_perf, timed
from sources import CameraThread, camera_samples, make_camera, replay_samples

NO_CAMERA = json.dumps({"status": "no_camera"})


async def run(args) -> None:
    cfg = load_config()
    configure_perf(cfg)
    clients = set()

    tracker = None
    if not args.replay:
        from pose import PoseTracker

        tracker = PoseTracker(cfg)

    async def handler(ws):
        clients.add(ws)
        try:
            async for msg in ws:  # 網頁端指令：開局 lock、回待機 unlock
                if msg in ("lock", "unlock") and tracker is not None:
                    tracker.lock.want_locked = msg == "lock"
        finally:
            clients.discard(ws)

    host, port = cfg["server"]["host"], cfg["server"]["port"]
    async with serve(handler, host, port):
        print(f"WebSocket: ws://{host}:{port}")
        detector = Detector(cfg)
        cam = None
        video_task = None
        if args.replay:
            samples = replay_samples(Path(args.replay))
        else:
            cam = CameraThread(make_camera(args.webcam, cfg), cfg["server"]["camera_retry_s"])
            cam.start()
            samples = camera_samples(cam, cfg, tracker=tracker)
            # 即時影像跟姿勢辨識分開跑：畫面維持相機幀率，不被辨識拖慢
            video_task = asyncio.create_task(stream_video(cam, clients, cfg["video"]))
        try:
            await pump(samples, detector, tracker, clients, args.verbose)
        finally:
            if video_task:
                video_task.cancel()
            if cam:
                cam.stop()


async def stream_video(cam: CameraThread, clients: set, c: dict) -> None:
    seq = 0
    while True:
        seq, frame = await cam.next_frame(seq)
        if frame is None or not clients:
            continue
        jpeg = await asyncio.to_thread(encode_jpeg, frame.rgb, c)
        broadcast(clients, jpeg)
        PERF.tick("video")


async def pump(samples, detector: Detector, tracker, clients: set, verbose: bool) -> None:
    last_kp = None
    async for sample in samples:
        if sample is None:
            broadcast(clients, NO_CAMERA)
            continue
        state = detector.update(sample)
        # 關鍵點：正規化影像座標 [x, y, visibility]，未鏡像（網頁端自己鏡像）
        lock = tracker.lock if tracker is not None else None
        state["locked"] = lock is not None and lock.locked is not None
        state["lock_match"] = None if lock is None or lock.last_match is None else round(lock.last_match, 3)
        # detector 沿用上一幀時（短暫漏偵測）骨架也沿用，畫面上的人和核彈瞄準點才不會跳
        kp = sample.kp or (last_kp if state["present"] else None)
        last_kp = kp
        state["kp"] = {k: [round(v, 4) for v in p] for k, p in kp.items()} if kp else None
        if verbose and (state["events"] or state["shaking"] or state["hands_up"]):
            print(state)
        broadcast(clients, json.dumps(state))


def encode_jpeg(rgb, c: dict) -> bytes:
    with timed(PERF, "video", "jpeg"):
        return _encode_jpeg(rgb, c)


def _encode_jpeg(rgb, c: dict) -> bytes:
    h, w = rgb.shape[:2]
    if w > c["width"]:
        rgb = cv2.resize(rgb, (c["width"], round(h * c["width"] / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, c["quality"]])
    return buf.tobytes()


def main() -> None:
    p = argparse.ArgumentParser(description="閃身步遊戲感測伺服器")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--webcam", type=int, metavar="INDEX", help="改用一般攝影機（無深度）")
    src.add_argument("--replay", metavar="FILE", help="回放 record.py 錄的 JSONL（循環播放）")
    p.add_argument("-v", "--verbose", action="store_true", help="印出觸發的動作")
    try:
        asyncio.run(run(p.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
