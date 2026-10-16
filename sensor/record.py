"""錄製關鍵點序列為 JSONL，給 server.py --replay 與調門檻用。

  uv run python record.py out.jsonl --seconds 20
  uv run python record.py out.jsonl --webcam 0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from detector import Detector, load_config
from sources import CameraThread, camera_samples, make_camera


async def run(args) -> None:
    cfg = load_config()
    detector = Detector(cfg)
    n = 0
    t_end = None
    cam = CameraThread(make_camera(args.webcam, cfg), cfg["server"]["camera_retry_s"])
    cam.start()
    with open(args.out, "w") as f:
        async for sample in camera_samples(cam, cfg):
            if sample is None:
                continue
            if t_end is None:
                t_end = time.monotonic() + args.seconds
                print(f"開始錄製 {args.seconds}s …")
            f.write(json.dumps(sample.to_dict()) + "\n")
            n += 1
            state = detector.update(sample)
            if state["events"] or state["shaking"] or state["hands_up"]:
                print(f"{sample.t:.2f}", state["events"], "shaking" if state["shaking"] else "", "hands_up" if state["hands_up"] else "")
            if time.monotonic() >= t_end:
                break
    cam.stop()
    print(f"完成：{n} 幀 → {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description="錄製關鍵點序列")
    p.add_argument("out", help="輸出 JSONL 路徑")
    p.add_argument("--seconds", type=float, default=15.0)
    p.add_argument("--webcam", type=int, metavar="INDEX", help="改用一般攝影機")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
