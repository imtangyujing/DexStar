#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SOURCE_ENV=".env.public"
TARGET_ENV=".env"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ENV=".env.backup.${STAMP}"

if [ ! -f "$SOURCE_ENV" ]; then
  echo "[错误] 未找到 ${SOURCE_ENV}，请先创建该文件。"
  exit 1
fi

if [ -f "$TARGET_ENV" ]; then
  cp "$TARGET_ENV" "$BACKUP_ENV"
  echo "[备份] 已备份当前 .env -> ${BACKUP_ENV}"
fi

cp "$SOURCE_ENV" "$TARGET_ENV"
echo "[完成] 已切换到对外开放环境配置（${SOURCE_ENV} -> ${TARGET_ENV}）"
echo "[下一步] 推荐启动命令：./scripts/demo-public.sh"
