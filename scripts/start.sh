#!/usr/bin/env bash
# 閃身步攤位一鍵啟動（start.command 會呼叫這支）。
#   SHAN_SOURCE=orbbec|webcam（預設 orbbec）
#   SHAN_SUDO=1|0：sensor 用 root 跑（orbbec 預設 1：macOS 的 UVCAssistant 會佔住相機；webcam 預設 0）
# 只有 sensor 是 root；uv、pnpm、vite、Chrome 一律用目前使用者跑。
set -euo pipefail

# Finder 雙擊時 PATH 很陽春
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SENSOR="$ROOT/sensor"
WEB="$ROOT/web"
SHAN_SOURCE="${SHAN_SOURCE:-orbbec}"
WEB_PORT=4173
SENSOR_PORT=8765
URL="http://localhost:$WEB_PORT"
# root 迴圈的 $0，帶本腳本 PID 才唯一；cleanup 用它找回 root 迴圈（sudo 不一定轉送 TERM）
LOOP_MARKER="shan-loop-$$"

case "$SHAN_SOURCE" in
  orbbec) SERVER_ARGS=(server.py); SHAN_SUDO="${SHAN_SUDO:-1}" ;;
  webcam) SERVER_ARGS=(server.py --webcam 0); SHAN_SUDO="${SHAN_SUDO:-0}" ;;
  *) echo "未知的 SHAN_SOURCE：$SHAN_SOURCE（orbbec|webcam）" >&2; exit 1 ;;
esac

for cmd in uv pnpm curl nc; do
  command -v "$cmd" >/dev/null || { echo "找不到 $cmd（PATH=$PATH）" >&2; exit 1; }
done

# 舊的還在跑就不要再開一份：port 會撞、相機會搶不到
for port in "$SENSOR_PORT" "$WEB_PORT"; do
  if nc -z localhost "$port" 2>/dev/null; then
    echo "port $port 已被佔用：上一次的閃身步可能還沒關。收掉：sudo pkill -f 'sensor/.venv/bin/python server.py'; pkill -f 'vite preview'" >&2
    exit 1
  fi
done
if nc -z localhost 8000 2>/dev/null; then
  echo "注意：port 8000 有東西在跑（風阻姿勢大挑戰？），它會佔住相機，閃身步會一直顯示沒有相機。" >&2
fi

# sudo 先問密碼，免得 build 完才卡在密碼提示
if [[ "$SHAN_SUDO" == "1" ]]; then
  sudo -v
fi

# 1. 依賴與前端 build（使用者身分）；dist 不存在或比原始碼舊才 build
uv sync --directory "$SENSOR" --inexact
[[ -d "$WEB/node_modules" ]] || pnpm --dir "$WEB" install
DIST_INDEX="$WEB/dist/index.html"
if [[ ! -f "$DIST_INDEX" ]] || [[ -n "$(find "$WEB/src" "$ROOT/audio" "$WEB/index.html" "$WEB/vite.config.ts" -newer "$DIST_INDEX" -print -quit)" ]]; then
  pnpm --dir "$WEB" build
fi

LOOP_PID=""
WEB_PID=""
KEEPALIVE_PID=""
cleanup() {
  if [[ -n "$WEB_PID" ]]; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  if [[ -n "$KEEPALIVE_PID" ]]; then
    kill "$KEEPALIVE_PID" 2>/dev/null || true
  fi
  if [[ -z "$LOOP_PID" ]]; then
    return
  fi
  if [[ "$SHAN_SUDO" == "1" ]]; then
    sudo -n kill -TERM "$LOOP_PID" 2>/dev/null || true
    # [s] 讓 pattern 不會比對到 pkill / sudo 自己的命令列；pkill 回 1 = 沒有符合，不算錯
    pk=0
    sudo -n pkill -TERM -f "[s]han-loop-$$" 2>/dev/null || pk=$?
    if [[ "$pk" -gt 1 ]] || ! sudo -n true 2>/dev/null; then
      echo "無法用 sudo 收掉 sensor，請手動執行：sudo pkill -f '$LOOP_MARKER'; sudo pkill -f 'sensor/.venv/bin/python server.py'" >&2
    fi
    # root 寫出來的檔案（模型下載、SDK log）改回目前使用者擁有
    for d in "$SENSOR/Log" "$SENSOR/models"; do
      [[ -e "$d" ]] && sudo -n chown -R "$(id -u):$(id -g)" "$d" 2>/dev/null || true
    done
  else
    pkill -P "$LOOP_PID" 2>/dev/null || true
    kill "$LOOP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
# 訊號一律轉成 exit，EXIT trap 才保證會跑（關掉 Terminal 視窗 = HUP）
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# 2. sensor：崩潰 2 秒後重啟。cwd = sensor（OrbbecSDK 的 Log/ 寫在 cwd）
PY="$SENSOR/.venv/bin/python"
# root 端的重啟迴圈：收到 TERM/INT/HUP 時連同 server 一起結束。用「背景 + wait」，trap 才能立刻生效。
read -r -d '' ROOT_LOOP <<'EOF' || true
child=""
trap 'if [ -n "$child" ]; then kill "$child" 2>/dev/null; wait "$child"; fi; exit 0' TERM INT HUP
until { "$@" & child=$!; wait "$child"; }; do
  child=""
  sleep 2
done
EOF

if [[ "$SHAN_SUDO" == "1" ]]; then
  # 不用 sudo uv run：uv cache 會變 root 擁有。PYTHONDONTWRITEBYTECODE：不留 root 的 __pycache__
  (cd "$SENSOR" && exec sudo /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
    /bin/bash -c "$ROOT_LOOP" "$LOOP_MARKER" "$PY" "${SERVER_ARGS[@]}") &
  LOOP_PID=$!
  # sudo 密碼快取預設 5 分鐘；cleanup 要用 sudo 收掉 root 迴圈，所以持續續期
  (
    while kill -0 "$$" 2>/dev/null; do
      sudo -n -v 2>/dev/null || true
      sleep 60
    done
  ) &
  KEEPALIVE_PID=$!
else
  (
    cd "$SENSOR"
    until "$PY" "${SERVER_ARGS[@]}"; do
      sleep 2
    done
  ) &
  LOOP_PID=$!
fi

# 3. 網頁：直接跑 vite 的 bin（shim 會 exec node，只有一個行程，好收）
"$WEB/node_modules/.bin/vite" preview --port "$WEB_PORT" --strictPort --outDir "$WEB/dist" "$WEB" &
WEB_PID=$!


# 無人攤位：本腳本活著期間不准螢幕／系統休眠；-w 讓 caffeinate 跟著本腳本結束
caffeinate -dimsu -w $$ &

# 4. 等網頁起來，開 kiosk（使用者身分）
until curl -sf "$URL" >/dev/null; do
  kill -0 "$WEB_PID" 2>/dev/null || { echo "vite preview 已結束" >&2; exit 1; }
  sleep 0.5
done
open -na "Google Chrome" --args --kiosk --app="$URL" --autoplay-policy=no-user-gesture-required
echo "閃身步已啟動（$SHAN_SOURCE）。結束：在這個視窗按 Ctrl-C，或直接關掉視窗。"
wait "$LOOP_PID"
