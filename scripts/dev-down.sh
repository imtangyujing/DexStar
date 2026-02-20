#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infra/docker/docker-compose.yml"
RUN_DIR=".dev-run"
API_PID_FILE="${RUN_DIR}/api.pid"
WORKER_PID_FILE="${RUN_DIR}/worker.pid"
WORKER_MODE_FILE="${RUN_DIR}/worker.mode"
WITH_INFRA="${1:-}"

kill_pid_file() {
  local pid_file="$1"
  local label="$2"
  if [ ! -f "$pid_file" ]; then
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    echo "[停止] 已停止 ${label} (PID: ${pid})"
  fi
  rm -f "$pid_file"
}

kill_residual_processes() {
  # uvicorn --reload 会派生子进程，可能不在 pid 文件里，做一次兜底清理。
  pkill -f "uvicorn apps.api.app.main:app" >/dev/null 2>&1 || true
  pkill -f "celery -A apps.worker.celery_app:celery_app worker" >/dev/null 2>&1 || true
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      for pid in $pids; do
        kill "$pid" >/dev/null 2>&1 || true
      done
    fi
  fi
}

echo "[停止] 正在停止本机开发进程..."
kill_pid_file "$API_PID_FILE" "API"
kill_pid_file "$WORKER_PID_FILE" "Worker"
kill_residual_processes

if [ -f "$WORKER_MODE_FILE" ] && [ "$(cat "$WORKER_MODE_FILE" 2>/dev/null || true)" = "docker" ]; then
  echo "[停止] 正在停止 Docker Worker..."
  docker compose -f "$COMPOSE_FILE" stop worker >/dev/null 2>&1 || true
fi
rm -f "$WORKER_MODE_FILE"

if [ "$WITH_INFRA" = "--with-infra" ]; then
  echo "[停止] 正在停止基础依赖容器（postgres/redis/minio）..."
  docker compose -f "$COMPOSE_FILE" stop postgres redis minio
else
  echo "[提示] 基础依赖容器仍在运行（下次 dev-up 更快）"
  echo "[提示] 若要一起停止容器: ./scripts/dev-down.sh --with-infra"
fi

echo "[完成] 开发模式已停止。"
