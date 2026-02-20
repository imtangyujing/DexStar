#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8080}"

cd "$ROOT_DIR/apps/api/app/static"

echo "[预览] 仅前端页面预览模式（不含真实下载能力）"
echo "[地址] http://localhost:${PORT}"
echo "[退出] 在当前终端按 Ctrl + C"
python3 -m http.server "$PORT"
