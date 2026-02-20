# GRAB V1

说唱伴奏下载网站（后端优先）MVP：支持提交 YouTube / B站公开视频链接，默认转为最高质量 MP3，并返回短期下载链接。

## 技术栈
- FastAPI + Celery + Redis + PostgreSQL
- yt-dlp + ffmpeg
- S3 兼容对象存储（本地默认 MinIO）

## 快速启动（Docker）
```bash
cp .env.example .env
docker compose -f infra/docker/docker-compose.yml up --build
```

API: `http://localhost:8000`
MinIO Console: `http://localhost:9001`

## 两个版本（本地测试 / 对外开放）
### 一键切换到本地测试版
```bash
cd /Users/jay/Documents/Dev/GRAB
./scripts/use-local-env.sh
./scripts/dev-up.sh
```

### 一键切换到对外开放版
```bash
cd /Users/jay/Documents/Dev/GRAB
./scripts/use-public-env.sh
./scripts/demo-public.sh
```

说明：
- 两个脚本都会先备份你当前 `.env`，再覆盖为目标版本配置。
- 仅切换配置不会改业务代码；要生效需要重启对应服务。
- 对外开放版依赖 `cloudflared`，并会自动把公网域名写回 `.env` 的 `STORAGE_PUBLIC_ENDPOINT` 和 `WECHAT_REDIRECT_URI`。

## 给不懂代码的测试步骤（推荐）
### 0. Desktop 工具测试（不依赖 Docker）
1. 打开终端，进入项目目录：
```bash
cd /Users/jay/Documents/Dev/GRAB
```
2. 启动桌面版：
```bash
./scripts/desktop-run.sh
```

说明：
- 这是本地桌面工具，直接用 `yt-dlp + ffmpeg` 下载为最高质量 MP3。
- 默认保存到 `~/Downloads`，也可在窗口里改目录。
- 这不会改动你现有后端代码或数据库，只是本机多开一个桌面窗口。
- 若系统 Python 的 `tkinter` 在你机器上不兼容，脚本会自动降级到命令行模式（仍可正常下载）。

### A. 立刻看网页（不装 Docker，纯预览）
1. 打开终端，进入项目目录：
```bash
cd /Users/jay/Documents/Dev/GRAB
```
2. 启动预览：
```bash
./scripts/preview-ui.sh
```
3. 浏览器打开：
- `http://localhost:8080`

说明：
- 这个模式只看网站页面，不会真的下载音频。
- 对项目代码几乎没有影响，只是临时启动了一个本地网页服务。

### B. 完整功能测试（需要 Docker）
1. 打开终端，进入项目目录：
```bash
cd /Users/jay/Documents/Dev/GRAB
```
2. 一键启动网站：
```bash
./scripts/demo-up.sh
```
3. 浏览器打开：
- `http://localhost:8000`

停止服务：
```bash
./scripts/demo-down.sh
```

说明：
- 这不会改坏你的项目代码，只会启动本地容器和本地数据卷。
- 你的代码文件仍在原目录，停止服务后代码不会丢失。

### C. 开发热更新模式（推荐日常改文案/改代码）
1. 打开终端，进入项目目录：
```bash
cd /Users/jay/Documents/Dev/GRAB
```
2. 启动开发模式：
```bash
./scripts/dev-up.sh
```
3. 浏览器打开：
- `http://localhost:8000`

停止开发模式：
```bash
./scripts/dev-down.sh
```

说明：
- 该模式会启动 `postgres/redis/minio` 容器，但 API/Worker 在本机运行。
- 默认是稳定模式（`DEV_RELOAD=false`），改代码后需重启一次 `./scripts/dev-up.sh`。
- 如需 API 热更新可这样启动：`DEV_RELOAD=true ./scripts/dev-up.sh`
- 如需连基础依赖容器一起停掉：`./scripts/dev-down.sh --with-infra`

### D. 公网模式（收集社区反馈）
1. 打开终端，进入项目目录：
```bash
cd /Users/jay/Documents/Dev/GRAB
```
2. 启动公网模式：
```bash
./scripts/demo-public.sh
```
3. 终端会输出可分享的公网地址（`https://*.trycloudflare.com`）。

停止公网模式：
```bash
./scripts/demo-public-down.sh
```

说明：
- 该模式会自动启动两条 Cloudflare Quick Tunnel：一条给网站/API，一条给下载链接。
- 脚本会自动写入 `.env`：`WECHAT_REDIRECT_URI` 和 `STORAGE_PUBLIC_ENDPOINT`，并重启 API 生效。
- Quick Tunnel 域名是临时的，重启后会变化；适合先做小范围公开测试。

### E. Chrome 插件版（Google 插件）
1. 先确保 API 可访问（本地 `http://localhost:8000` 或你的公网域名）。
2. 打开 Chrome：
- 地址栏输入 `chrome://extensions`
- 打开右上角「开发者模式」
- 点「加载已解压的扩展程序」
- 选择目录：`/Users/jay/Documents/Dev/GRAB/apps/chrome_extension`
3. 在插件页面点「设置」：
- `API 地址` 填你的服务地址（例如 `https://app.grabhiphop.top`）
- 若后端开启鉴权，可填 `Token`；游客模式可留空
4. 回到插件弹窗，粘贴视频链接，点击「创建任务并处理」。

可选：打包 zip 分发
```bash
cd /Users/jay/Documents/Dev/GRAB
./scripts/build-chrome-extension.sh
```
输出文件：`/Users/jay/Documents/Dev/GRAB/dist/grab-chrome-extension.zip`

## 主要接口
- `GET /api/v1/auth/wechat/login-url`
- `GET /api/v1/auth/wechat/callback`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/cancel`

## 本地开发
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn apps.api.app.main:app --reload
celery -A apps.worker.celery_app:celery_app worker --loglevel=INFO
```

## 说明
- V1 固定输出 `mp3`，并使用最高质量（`best`）。
- 下载流程会尽量抓取视频封面并嵌入 MP3（失败会自动降级，不影响下载）。
- 默认开启 BPM + 标题规则命名；调性分析默认关闭。
- BPM 默认走 `Essentia` 严格模式（`auto` 等同于 `essentia`，失败时返回 unknown，不走低精度回退）。
- 后端选择可通过环境变量控制：
  - `ENABLE_BPM_KEY_ANALYSIS=true|false`（默认 `true`，仅控制 BPM）
  - `ANALYSIS_BPM_BACKEND=auto|essentia|tempo_cnn_vote`
  - `ANALYSIS_KEY_BACKEND=auto|essentia|madmom`
  - `TEMPO_CNN_GRAPH_PATH`（仅 `tempo_cnn_vote` 使用）
- 本项目 Docker Worker 已内置 `essentia-tensorflow==2.1b6.dev1389`（`linux/amd64`）。
- 实验模式：`tempo_cnn_vote` 使用 `TempoCNN + localTempo 概率加权多数投票` 聚合 BPM。
- Apple Silicon（M1/M2/M3）本机 Python 通常装不上可用 Essentia，建议直接用 Docker 路径：
```bash
./scripts/demo-up.sh
# 或开发模式（会自动在本机/容器间切换 worker）
./scripts/dev-up.sh
```
- B站受限内容（登录/会员/地区）会返回 `SOURCE_RESTRICTED`。
- 文件短期缓存策略通过对象存储生命周期规则配置，默认目标是 24h 自动清理。
- 下载链接对外访问地址可通过 `STORAGE_PUBLIC_ENDPOINT` 配置（本地 Docker 推荐 `http://localhost:9000`）。
- 对象文件会按 `OBJECT_RETENTION_HOURS` 自动配置桶生命周期删除（S3/MinIO 以“天”为单位执行，24 即 1 天）。
- 微信扫码登录需要微信开放平台网站应用配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，并把回调地址设为 `WECHAT_REDIRECT_URI`。
- 开发联调可先用 `WECHAT_AUTH_BYPASS=true`（模拟登录）。
- 当前版本暂不提供 Google 登录入口。
- 当前默认开启 `AUTH_DISABLED=true`（游客免登录模式），微信登录入口已在前端临时隐藏。
- 命名规则默认不依赖 AI；仅当 `ENABLE_AI_NAMING_FALLBACK=true` 时才使用 OpenAI 兜底。
- AI 配置通过环境变量注入：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`AI_TIMEOUT_SECONDS`、`AI_MAX_RETRIES`。
