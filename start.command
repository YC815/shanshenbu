#!/bin/bash
# Finder 雙擊啟動閃身步。改用一般攝影機：把 orbbec 改成 webcam。
# 會先問一次電腦密碼（Orbbec 在 macOS 要 root）。結束：Ctrl-C 或關掉這個視窗。
cd "$(dirname "$0")"
export SHAN_SOURCE="${SHAN_SOURCE:-orbbec}"
exec scripts/start.sh
