#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infra/docker/docker-compose.yml"
API_PID_FILE=".cloudflared-api.pid"
MINIO_PID_FILE=".cloudflared-minio.pid"
API_LOG_FILE=".cloudflared-api.log"
MINIO_LOG_FILE=".cloudflared-minio.log"

require_cmd() {
  local cmd="$1"
  local tip="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[错误] 没有检测到 ${cmd}。${tip}"
    exit 1
  fi
}

stop_pid_file() {
  local pid_file="$1"
  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "${pid}" ] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$pid_file"
}

wait_tunnel_url() {
  local log_file="$1"
  local label="$2"
  local url=""
  local i=0
  while [ "$i" -lt 60 ]; do
    if [ -f "$log_file" ]; then
      url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$log_file" | head -n 1 || true)"
      if [ -n "$url" ]; then
        printf '%s' "$url"
        return 0
      fi
    fi
    i=$((i + 1))
    sleep 1
  done

  echo "[错误] ${label} 公网通道创建超时。请查看日志: ${log_file}" >&2
  if [ -f "$log_file" ]; then
    tail -n 30 "$log_file" >&2
  fi
  return 1
}

upsert_env() {
  local key="$1"
  local value="$2"
  local tmp_file=".env.tmp.$$"

  awk -v key="$key" -v value="$value" '
    BEGIN { replaced=0 }
    $0 ~ "^" key "=" {
      print key "=" value
      replaced=1
      next
    }
    { print }
    END {
      if (!replaced) {
        print key "=" value
      }
    }
  ' .env > "$tmp_file"

  mv "$tmp_file" .env
}

cleanup_on_error() {
  stop_pid_file "$API_PID_FILE"
  stop_pid_file "$MINIO_PID_FILE"
}

trap cleanup_on_error ERR INT TERM

require_cmd "docker" "请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
require_cmd "cloudflared" "请先安装 cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"

if ! docker info >/dev/null 2>&1; then
  echo "[错误] Docker 未启动，请先打开 Docker Desktop。"
  exit 1
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[提示] 已创建 .env（来自 .env.example）"
fi

stop_pid_file "$API_PID_FILE"
stop_pid_file "$MINIO_PID_FILE"
rm -f "$API_LOG_FILE" "$MINIO_LOG_FILE"

echo "[启动] 正在构建并启动服务..."
docker compose -f "$COMPOSE_FILE" up --build -d

echo "[启动] 正在创建 API 公网通道..."
cloudflared tunnel --url "http://localhost:8000" --no-autoupdate > "$API_LOG_FILE" 2>&1 &
echo "$!" > "$API_PID_FILE"

echo "[启动] 正在创建下载通道..."
cloudflared tunnel --url "http://localhost:9000" --no-autoupdate > "$MINIO_LOG_FILE" 2>&1 &
echo "$!" > "$MINIO_PID_FILE"

API_URL="$(wait_tunnel_url "$API_LOG_FILE" "API")"
MINIO_URL="$(wait_tunnel_url "$MINIO_LOG_FILE" "下载")"

upsert_env "WECHAT_REDIRECT_URI" "${API_URL}/api/v1/auth/wechat/callback"
upsert_env "STORAGE_PUBLIC_ENDPOINT" "${MINIO_URL}"

echo "[更新] 已写入 .env:"
echo "        WECHAT_REDIRECT_URI=${API_URL}/api/v1/auth/wechat/callback"
echo "        STORAGE_PUBLIC_ENDPOINT=${MINIO_URL}"

echo "[重建] 正在重建 API/Worker 使新配置生效..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate api worker

trap - ERR INT TERM

echo "[完成] 公网地址: ${API_URL}"
echo "[完成] 下载地址域名: ${MINIO_URL}"
echo "[日志] API 通道日志: ${API_LOG_FILE}"
echo "[日志] 下载通道日志: ${MINIO_LOG_FILE}"
echo "[提示] 若页面里已有旧下载链接，请刷新任务状态或重新创建任务。"
echo "[停止] 运行: ./scripts/demo-public-down.sh"
