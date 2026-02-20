#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/apps/chrome_extension"
OUT_DIR="$ROOT_DIR/dist"
OUT_FILE="$OUT_DIR/grab-chrome-extension.zip"

if [ ! -d "$SRC_DIR" ]; then
  echo "[错误] 未找到插件目录: $SRC_DIR"
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "[错误] 未找到 zip 命令，请先安装 zip。"
  exit 1
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT_FILE"

(
  cd "$SRC_DIR"
  zip -r "$OUT_FILE" . -x '*.DS_Store'
)

echo "[完成] 插件打包完成: $OUT_FILE"
