#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infra/docker/docker-compose.yml"
API_PID_FILE=".cloudflared-api.pid"
MINIO_PID_FILE=".cloudflared-minio.pid"
API_LOG_FILE=".cloudflared-api.log"
MINIO_LOG_FILE=".cloudflared-minio.log"

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "${pid}" ] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    echo "[停止] 已关闭 ${label} 通道 (PID: ${pid})"
  fi
  rm -f "$pid_file"
}

echo "[停止] 正在关闭公网通道..."
stop_pid_file "$API_PID_FILE" "API"
stop_pid_file "$MINIO_PID_FILE" "下载"
rm -f "$API_LOG_FILE" "$MINIO_LOG_FILE"

echo "[停止] 正在停止服务..."
docker compose -f "$COMPOSE_FILE" down

echo "[完成] 公网模式已停止。"
