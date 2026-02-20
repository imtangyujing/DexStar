#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infra/docker/docker-compose.yml"
RUN_DIR=".dev-run"
API_PID_FILE="${RUN_DIR}/api.pid"
WORKER_PID_FILE="${RUN_DIR}/worker.pid"
WORKER_MODE_FILE="${RUN_DIR}/worker.mode"
API_LOG_FILE="${RUN_DIR}/api.log"
WORKER_LOG_FILE="${RUN_DIR}/worker.log"
DEV_RELOAD="${DEV_RELOAD:-false}"

require_cmd() {
  local cmd="$1"
  local tip="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[错误] 缺少命令 ${cmd}。${tip}"
    exit 1
  fi
}

kill_pid_file() {
  local pid_file="$1"
  if [ ! -f "$pid_file" ]; then
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$pid_file"
}

require_cmd "docker" "请先安装 Docker Desktop。"
require_cmd "curl" "请先安装 curl。"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[提示] 已创建 .env（来自 .env.example）"
fi

if ! docker info >/dev/null 2>&1; then
  echo "[错误] Docker 未启动，请先打开 Docker Desktop。"
  exit 1
fi

python_has_base_modules() {
  local py="$1"
  "$py" - <<'PY' >/dev/null 2>&1
import importlib.util
# API + worker 共用的基础依赖。
base_mods = ["uvicorn", "celery", "librosa", "mutagen"]
ok = all(importlib.util.find_spec(m) is not None for m in base_mods)
raise SystemExit(0 if ok else 1)
PY
}

python_has_module() {
  local py="$1"
  local module_name="$2"
  "$py" - "$module_name" <<'PY' >/dev/null 2>&1
import importlib.util
import sys
name = sys.argv[1]
raise SystemExit(0 if importlib.util.find_spec(name) is not None else 1)
PY
}

pick_python() {
  local candidates=()
  local clt_python="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python"

  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    candidates+=("${ROOT_DIR}/.venv/bin/python")
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    candidates+=("$(command -v python3.11)")
  fi
  if [ -x "/usr/bin/python3" ]; then
    candidates+=("/usr/bin/python3")
  fi
  if command -v python3 >/dev/null 2>&1; then
    candidates+=("$(command -v python3)")
  fi
  if [ -x "$clt_python" ]; then
    candidates+=("$clt_python")
  fi

  local py
  for py in "${candidates[@]}"; do
    if python_has_base_modules "$py"; then
      printf '%s' "$py"
      return 0
    fi
  done
  return 1
}

REQUESTED_BPM_BACKEND="$(awk -F= '/^ANALYSIS_BPM_BACKEND=/{print tolower($2)}' .env | tail -n 1)"
if [ -z "$REQUESTED_BPM_BACKEND" ]; then
  REQUESTED_BPM_BACKEND="auto"
fi

if ! PYTHON_BIN="$(pick_python)"; then
  echo "[错误] 找不到可用 Python 环境（需包含 uvicorn + celery + librosa + mutagen）。"
  echo "[提示] 可执行：python3 -m venv .venv && ./.venv/bin/pip install -e '.[dev]'"
  exit 1
fi

LOCAL_HAS_ESSENTIA=0
if python_has_module "$PYTHON_BIN" "essentia"; then
  LOCAL_HAS_ESSENTIA=1
fi

WORKER_MODE="local"
case "$REQUESTED_BPM_BACKEND" in
  auto|essentia)
    # Essentia 在 Apple Silicon 的本机 Python 上常不可用；
    # 这里自动切到 Docker worker（amd64）保证链路可用。
    if [ "$LOCAL_HAS_ESSENTIA" -ne 1 ]; then
      WORKER_MODE="docker"
    fi
    ;;
  tempo_cnn_vote)
    # TempoCNN 依赖 essentia-tensorflow + 模型文件，开发环境固定走 docker worker。
    WORKER_MODE="docker"
    ;;
  *)
    echo "[错误] 当前为 Essentia 严格模式，ANALYSIS_BPM_BACKEND 仅允许 auto、essentia 或 tempo_cnn_vote。"
    echo "[提示] 请修改 .env 为 ANALYSIS_BPM_BACKEND=auto"
    exit 1
    ;;
esac

mkdir -p "$RUN_DIR"
kill_pid_file "$API_PID_FILE"
kill_pid_file "$WORKER_PID_FILE"
rm -f "$WORKER_MODE_FILE"

cleanup_on_error() {
  kill_pid_file "$API_PID_FILE"
  kill_pid_file "$WORKER_PID_FILE"
  if [ "${WORKER_MODE:-local}" = "docker" ]; then
    docker compose -f "$COMPOSE_FILE" stop worker >/dev/null 2>&1 || true
  fi
}
trap cleanup_on_error ERR INT TERM

echo "[启动] 开发模式：先启动基础依赖（postgres/redis/minio）..."
docker compose -f "$COMPOSE_FILE" up -d postgres redis minio

echo "[启动] 停止容器里的 api，切换为本机热更新..."
docker compose -f "$COMPOSE_FILE" stop api >/dev/null 2>&1 || true
if [ "$WORKER_MODE" = "local" ]; then
  docker compose -f "$COMPOSE_FILE" stop worker >/dev/null 2>&1 || true
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "[警告] 未检测到 yt-dlp，下载任务会失败。可安装: brew install yt-dlp"
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[警告] 未检测到 ffmpeg，转码任务会失败。可安装: brew install ffmpeg"
fi

COMMON_ENV=(
  "PYTHONUNBUFFERED=1"
  "DATABASE_URL=postgresql+psycopg://grab:grab@localhost:5432/grab"
  "REDIS_URL=redis://localhost:6379/0"
  "CELERY_BROKER_URL=redis://localhost:6379/1"
  "CELERY_RESULT_BACKEND=redis://localhost:6379/2"
  "STORAGE_ENDPOINT=http://localhost:9000"
  "STORAGE_PUBLIC_ENDPOINT=http://localhost:9000"
  "WECHAT_REDIRECT_URI=http://localhost:8000/api/v1/auth/wechat/callback"
)

echo "[启动] 本机 API（热更新）..."
API_CMD=("$PYTHON_BIN" -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000)
if [ "$DEV_RELOAD" = "true" ]; then
  API_CMD+=("--reload")
fi
nohup env "${COMMON_ENV[@]}" "${API_CMD[@]}" >"$API_LOG_FILE" 2>&1 &
echo "$!" >"$API_PID_FILE"

if [ "$WORKER_MODE" = "docker" ]; then
  echo "[启动] Docker Worker（Essentia，amd64）..."
  docker compose -f "$COMPOSE_FILE" up -d --build worker
  printf '%s' "docker" >"$WORKER_MODE_FILE"
  rm -f "$WORKER_PID_FILE"
else
  echo "[启动] 本机 Worker..."
  nohup env "${COMMON_ENV[@]}" "$PYTHON_BIN" -m celery -A apps.worker.celery_app:celery_app worker --loglevel=INFO --concurrency=2 >"$WORKER_LOG_FILE" 2>&1 &
  echo "$!" >"$WORKER_PID_FILE"
  printf '%s' "local" >"$WORKER_MODE_FILE"
fi

echo "[等待] 检查 API 健康状态..."
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:8000/healthz" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

if [ "$ok" -ne 1 ]; then
  echo "[错误] API 未启动成功，请看日志: ${API_LOG_FILE}"
  tail -n 40 "$API_LOG_FILE" || true
  exit 1
fi

trap - ERR INT TERM
echo "[完成] 开发模式已启动"
echo "[地址] 网站: http://localhost:8000"
echo "[模式] API 热更新: ${DEV_RELOAD}"
echo "[模式] Worker: ${WORKER_MODE}"
echo "[配置] ANALYSIS_BPM_BACKEND: ${REQUESTED_BPM_BACKEND}"
echo "[日志] API: ${API_LOG_FILE}"
if [ "$WORKER_MODE" = "docker" ]; then
  echo "[日志] Worker: docker compose -f ${COMPOSE_FILE} logs -f worker"
else
  echo "[日志] Worker: ${WORKER_LOG_FILE}"
fi
echo "[停止] 运行: ./scripts/dev-down.sh"
