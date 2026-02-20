#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_CMD="python3"
if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
elif [ -x "/opt/homebrew/bin/python3" ]; then
  PYTHON_CMD="/opt/homebrew/bin/python3"
elif [ -x "/usr/local/bin/python3" ]; then
  PYTHON_CMD="/usr/local/bin/python3"
fi

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "[错误] 未检测到 python3。"
  exit 1
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "[错误] 未检测到 yt-dlp。macOS 可执行: brew install yt-dlp"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[错误] 未检测到 ffmpeg。macOS 可执行: brew install ffmpeg"
  exit 1
fi

PYTHON_BIN="$("$PYTHON_CMD" - <<'PY'
import sys
print(sys.executable)
PY
)"
PYTHON_MINOR="$("$PYTHON_CMD" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

can_run_gui() {
  "$PYTHON_CMD" - <<'PY' >/dev/null 2>&1
import _tkinter  # noqa: F401
import tkinter  # noqa: F401
PY
}

if [[ "$PYTHON_BIN" == *"/Library/Developer/CommandLineTools/"* ]]; then
  echo "[警告] 当前系统 Python 的 tkinter 不可用，已切换到命令行模式。"
  echo "[提示] 如需图形界面，可安装 Homebrew Python 后重试: brew install python"
  "$PYTHON_CMD" -m desktop.cli
elif ! can_run_gui; then
  echo "[警告] 当前 Python 缺少 tkinter(_tkinter)，已切换到命令行模式。"
  echo "[提示] 可执行: brew install python-tk@${PYTHON_MINOR}"
  "$PYTHON_CMD" -m desktop.cli
else
  echo "[启动] GRAB Desktop 图形界面"
  if ! "$PYTHON_CMD" -m desktop.app; then
    echo "[警告] 图形界面启动失败，已自动切换到命令行模式。"
    "$PYTHON_CMD" -m desktop.cli
  fi
fi
