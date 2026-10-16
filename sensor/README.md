# sensor

Orbbec Gemini 336L + MediaPipe Pose → WebSocket（ws://localhost:8765）。

## 攤位啟動

Finder 雙擊 `shanshunboo/start.command`：問一次電腦密碼 → sensor（root）＋網頁（vite preview :4173）→ Chrome kiosk。
結束：視窗裡 Ctrl-C 或直接關視窗。改用一般攝影機：把 `start.command` 裡的 `orbbec` 改成 `webcam`。
風阻姿勢大挑戰（port 8000）開著時會佔住相機，先關掉它。

## 效能相關設定（config.toml）

- `[pose] delegate = "gpu"`：MediaPipe 改用 Metal，失敗自動退回 cpu。30Hz 節奏下實測和 CPU 差不多（見 config.toml），預設不開。GPU 的 visibility 和 CPU 會差到約 0.2，切換後要重看 `min_hip_visibility` 等門檻。
- `[camera] align = "hw"`：相機硬體對齊，省掉 CPU 的 AlignFilter；開不起來自動退回 sw。
- `[camera] depth = "low"`：同 fps 最小的 depth 解析度。
- `[perf] log_s = 5`：每 5 秒印一行 `perf 5s | camera …Hz wait align decode depth | pose …Hz detect total | video …Hz jpeg`（ms 中位數）。

## 手動執行

```sh
sudo .venv/bin/python server.py      # Gemini 336L：macOS 必須 root（UVCAssistant 會佔住相機），不要用 sudo uv run
uv run python server.py --webcam 0   # 一般攝影機，距離用肩寬估
uv run python server.py --replay rec.jsonl -v
uv run python record.py rec.jsonl --seconds 20
uv run pytest
```

首次執行會下載 `models/pose_landmarker_lite.task`。門檻在 `config.toml`。
