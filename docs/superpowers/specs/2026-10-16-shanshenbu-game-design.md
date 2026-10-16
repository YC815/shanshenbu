# 閃身步核彈閃避遊戲 — 設計

日期：2026-10-16

## 目標

用 Orbbec Gemini 336L 深度相機做一個體感遊戲：玩家從場地後方往鏡頭前進，途中用「閃身步」閃避左右飛來的核彈、用「狗熊哆嗦毛」閃避上方落下的核彈，走到終點後雙手舉高 3 秒獲勝。每人 3 滴血。

動作來源：網路爆紅的花鼓燈「閃身步」（參考影片 https://www.youtube.com/watch?v=cp6iWgPdfTI）與鼓子秧歌「狗熊哆嗦毛」（腰腹帶動大臂，全身大幅抖動）。

## 範圍

- 單人遊玩，輪流上場。
- 不做：多人同場、排行榜、音效、美術素材（第一版用幾何圖形）、帳號。

## 架構

Python 只負責「看」並輸出事件；遊戲規則全部在網頁端。

```
Gemini 336L ──▶ [sensor/ Python, uv]                    [web/ Vite + TS + Canvas]
                camera.py   RGB + 對齊深度               input/  SensorInput (WebSocket)
                pose.py     MediaPipe 33 點 + 每點深度           KeyboardInput
                detector.py 動作判定（純函式）           game/   狀態機、核彈、命中判定
                server.py   WebSocket :8765 ──JSON──▶   render/ Canvas 2D
                record.py   錄製關鍵點序列為 JSONL
```

### Python 端（`sensor/`）

- 套件：`pyorbbecsdk`、`mediapipe`、`websockets`、`numpy`，以 uv 管理。
- `camera.py`：開啟 Gemini 336L 的 color 與 depth stream，深度對齊到彩色畫面，輸出 `Frame{rgb, depth, intrinsics, t}`。
- `pose.py`：MediaPipe Pose（`num_poses=1`）取 33 個關鍵點，查對齊深度並以內參換算為公尺座標。
- `detector.py`：輸入關鍵點時間序列，輸出每幀的感測狀態。純函式／純狀態物件，不碰 I/O。
- `server.py`：每幀推送一則 JSON。支援 `--replay <file.jsonl>` 以錄製檔取代相機。
- `record.py`：把關鍵點與深度序列存成 JSONL，供測試與回放。
- 所有門檻放在 `sensor/config.toml`。

### 通訊協定（Python → 網頁，每幀一則）

```json
{ "status": "ok", "present": true, "distance_m": 2.8, "x_m": -0.1,
  "events": ["step_right"], "shaking": false, "hands_up": false }
```

- `status`：`"ok"` 或 `"no_camera"`。`no_camera` 時其餘欄位省略。
- `events`：該幀觸發的一次性事件，值為 `step_left`／`step_right`。
- `shaking`、`hands_up`：持續狀態布林值，持續時間由網頁端累計。
- `x_m`：髖部中心的橫向位置（公尺，玩家視角，右為正）。
- 左右一律以**玩家視角**定義。

### 網頁端（`web/`）

- Vite + TypeScript + Canvas 2D，全螢幕單頁，不使用框架。
- `input/`：`SensorInput` 與 `KeyboardInput` 實作同一介面 `Input`，每幀提供與協定相同形狀的狀態。
  - 鍵盤：`←`/`→` 閃身步、`Space` 按住為哆嗦毛、`↑`/`↓` 調整距離（每次 0.25 m）、`H` 按住為舉手、`K` 切換鍵盤模式。
- `game/`：遊戲狀態機與核彈邏輯，純邏輯，不碰 DOM。
- `render/`：Canvas 繪製，畫面鏡像；含 debug 面板顯示感測數值。

## 動作判定

以髖部中心（MediaPipe 23、24 號點中點）的 3D 座標為主。

| 動作 | 判定 | 預設值 |
|---|---|---|
| 閃身步 | 0.4 s 內髖部中心橫向位移 ≥ 0.25 m，方向即事件方向 | 觸發後冷卻 0.5 s |
| 狗熊哆嗦毛 | 雙肘、雙腕 2D 速度以肩寬正規化後，0.6 s 滑動窗平均值 > 門檻 | 門檻現場調校 |
| 舉手 | 雙手腕 y 座標皆高於鼻子 | — |
| 距離 | 髖部周圍深度的中位數，忽略 0 值 | — |
| 在場 | MediaPipe 偵測到人且髖部可見度 ≥ 0.5 | — |

## 遊戲規則

場地：距鏡頭 ≥ 3.5 m 為起點，≤ 1.5 m 為終點。

1. **IDLE**：提示站到起點。`present` 且 `distance_m ≥ 3.5` 持續 1 s → 倒數 3、2、1 → `PLAYING`。
2. **PLAYING**：
   - 進度 = `clamp((3.5 − d) / 2.0, 0, 1)`。
   - 核彈三種：左方來（需 `step_right`）、右方來（需 `step_left`）、上方來（需判定窗內 `shaking` 累計 ≥ 0.5 s）。類型隨機均分。
   - 每顆核彈：警示 → 飛行 2 s；最後 1 s 為判定窗，窗外的動作不算。窗內完成即閃過；判定窗結束仍未完成 → 扣 1 滴血。
   - 同一時間最多一顆核彈。
   - 生成間隔（上一顆結算到下一顆警示）由進度 0 時 3.0 s 線性縮至進度 1 時 1.2 s。
   - 血量 3，歸零 → `LOSE`。
3. **終點**：`distance_m ≤ 1.5` 時不再生成新核彈，已在飛的照常判定。在終點內 `hands_up` 連續 3 s → `WIN`；中途放下或離開終點區則歸零。
4. **離場**：`present` 為 false 連續 2 s → 本局作廢，回 `IDLE`。
5. **WIN／LOSE**：結算畫面 5 s 後回 `IDLE`。

## 錯誤處理

- 相機未接或斷線：Python 每 2 s 重試並推送 `{"status":"no_camera"}`；網頁顯示「相機未連線」，可按 `K` 切鍵盤模式。
- WebSocket 斷線：網頁每 1 s 重連；`PLAYING` 中斷線則暫停並顯示「感測器斷線」，重連後繼續。
- 深度破洞：中位數忽略 0；整區無有效值時沿用上一幀距離。
- 多人入鏡：已知限制，MediaPipe 只追一人，可能追錯；畫面提示「場地內只能一個人」。

## 測試

- `sensor/`：pytest 以合成關鍵點序列測 `detector.py`：閃身步左右觸發與冷卻、哆嗦毛觸發、舉手、靜止小晃動不誤觸。
- `server.py --replay`：以 `record.py` 錄下的真人 JSONL 回放，無相機也可重現與調門檻。
- `web/`：vitest 測 `game/` 狀態機：判定窗內外、扣血、死亡、終點不生成、勝利計時與歸零、離場作廢。
- 實機調校：接上相機後由使用者現場做動作調整 `config.toml`。

## 已知風險

- `pyorbbecsdk` 在 macOS Apple Silicon 是否可用未經驗證，需接相機實測。不可用時的退路：改用 OrbbecSDK C++ 撰寫 `camera.py` 等價模組，或改在 Windows／Linux 執行 `sensor/`。
