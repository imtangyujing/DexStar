#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 没有检测到 docker。请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
  exit 1
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[提示] 已创建 .env（来自 .env.example）"
fi

echo "[启动] 正在构建并启动服务，这一步第一次会稍慢..."
docker compose -f infra/docker/docker-compose.yml up --build -d

echo "[完成] 网站地址: http://localhost:8000"
echo "[信息] MinIO 控制台: http://localhost:9001"
echo "[停止] 运行: ./scripts/demo-down.sh"
