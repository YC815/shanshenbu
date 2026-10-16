# 閃身步・核彈閃避

深度相機體感遊戲：核彈從旁邊飛來就用「閃身步」躲開，從頭上掉下來的追蹤導彈就用「狗熊哆嗦毛」全身用力抖掉。閃過 10 顆獲勝，被炸 3 次出局。

動作來源：花鼓燈「閃身步」與鼓子秧歌「狗熊哆嗦毛」。

## 架構

```
Orbbec Gemini 336L ──▶ sensor/（Python, uv）           ──WebSocket──▶ web/（Vite + TS + Canvas）
（或一般 webcam）       MediaPipe Pose、玩家鎖定、動作判定                 遊戲規則、畫面、音效
```

- `sensor/`：相機、姿勢辨識、動作判定，門檻在 `sensor/config.toml`。細節見 [sensor/README.md](sensor/README.md)。
- `web/`：遊戲狀態機與畫面。
- `audio/`：動作提示音不附在 repo 裡，見 [audio/README.md](audio/README.md)。

## 執行

需要 macOS、[uv](https://docs.astral.sh/uv/)、pnpm、Google Chrome。

```sh
./start.command                      # Orbbec Gemini 336L（會問一次密碼：macOS 上要 root 才能開相機）
SHAN_SOURCE=webcam ./start.command   # 一般攝影機，距離用肩寬估
```

會自動安裝依賴、build 網頁、用 Chrome kiosk 開啟。結束：在終端機按 Ctrl-C。

沒有相機時可以用鍵盤玩：網址加 `?kb`，或遊戲中按 `K` 切換。`←`/`→` 橫移、`Space` 按住哆嗦毛、`H` 按住舉手、`D` 開關除錯面板。

## 玩法

1. 站到地上的腳印，雙手舉過頭頂 1.5 秒開始。
2. 側方核彈打向它出現時你站的位置：飛到之前離開那裡（左右跨、前後跨、蹲下都行）。
3. 頭上的追蹤導彈會跟著你：持續全身抖動才甩得掉。

## 測試

```sh
cd sensor && uv run pytest
cd web && pnpm test
```
