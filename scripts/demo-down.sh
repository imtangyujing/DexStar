#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[停止] 正在停止服务..."
docker compose -f infra/docker/docker-compose.yml down

echo "[完成] 服务已停止。"
