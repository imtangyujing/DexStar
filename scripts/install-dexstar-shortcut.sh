#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ICON_PATH="${ROOT_DIR}/media/YTDownload.png"

APP_PATH="${HOME}/Desktop/DexStar.app"
CONTENTS_DIR="${APP_PATH}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
INFO_PLIST="${CONTENTS_DIR}/Info.plist"
LAUNCHER_PATH="${MACOS_DIR}/DexStar"

if ! command -v iconutil >/dev/null 2>&1; then
  echo "[错误] 未检测到 iconutil，无法生成应用图标。"
  exit 1
fi

if ! command -v sips >/dev/null 2>&1; then
  echo "[错误] 未检测到 sips，无法生成应用图标。"
  exit 1
fi

if [ ! -f "$ICON_PATH" ]; then
  echo "[错误] 未找到图标素材：$ICON_PATH"
  exit 1
fi

rm -rf "$APP_PATH"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$ROOT_DIR"
LOG_PATH="\${HOME}/Library/Logs/DexStar.app.log"
export PATH="\${HOME}/.local/bin:\${HOME}/tools/ffmpeg:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\${PATH:-}"
mkdir -p "\${HOME}/Library/Logs"
exec >> "\$LOG_PATH" 2>&1

show_error() {
  local message="\$1"
  echo "[错误] \$message"
  if command -v osascript >/dev/null 2>&1; then
    /usr/bin/osascript - "\$message" <<'APPLESCRIPT'
on run argv
  set msg to item 1 of argv
  display dialog msg buttons {"知道了"} default button "知道了" with icon stop
end run
APPLESCRIPT
  fi
}

PYTHON_CMD="python3"
if [ -x "\${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_CMD="\${ROOT_DIR}/.venv/bin/python"
elif [ -x "/opt/homebrew/bin/python3" ]; then
  PYTHON_CMD="/opt/homebrew/bin/python3"
elif [ -x "/usr/local/bin/python3" ]; then
  PYTHON_CMD="/usr/local/bin/python3"
fi

if ! command -v "\$PYTHON_CMD" >/dev/null 2>&1; then
  show_error "未检测到 python3。"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 && [ -x "\${HOME}/tools/ffmpeg/ffmpeg" ]; then
  mkdir -p "\${HOME}/.dexstar-bin"
  ln -sf "\${HOME}/tools/ffmpeg/ffmpeg" "\${HOME}/.dexstar-bin/ffmpeg"
  export PATH="\${HOME}/.dexstar-bin:\$PATH"
fi

PYTHON_BIN="\$("\$PYTHON_CMD" - <<'PY'
import sys
print(sys.executable)
PY
)"
PYTHON_MINOR="\$("\$PYTHON_CMD" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

can_run_gui() {
  "\$PYTHON_CMD" - <<'PY' >/dev/null 2>&1
import _tkinter  # noqa: F401
import tkinter  # noqa: F401
PY
}

if [[ "\$PYTHON_BIN" == *"/Library/Developer/CommandLineTools/"* ]]; then
  show_error "当前 Python 不支持 tkinter。建议执行：brew install python"
  exit 1
fi

if ! can_run_gui; then
  show_error "当前 Python 缺少 tkinter(_tkinter)。建议执行：brew install python-tk@\${PYTHON_MINOR}"
  exit 1
fi

cd "\$ROOT_DIR"
echo "[启动] DexStar Desktop 图形界面"
if ! "\$PYTHON_CMD" -m desktop.dexstar_app; then
  show_error "图形界面启动失败，请查看 \$LOG_PATH"
  exit 1
fi
EOF
chmod +x "$LAUNCHER_PATH"
chmod +x "$ROOT_DIR/scripts/dexstar-desktop-run.sh"

cat > "$INFO_PLIST" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>DexStar</string>
    <key>CFBundleIconFile</key>
    <string>DexStar.icns</string>
    <key>CFBundleIconName</key>
    <string>DexStar</string>
    <key>CFBundleIdentifier</key>
    <string>com.jay.dexstar.shortcut</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>DexStar</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSUIElement</key>
    <false/>
  </dict>
</plist>
EOF

TMP_DIR="$(mktemp -d)"
ICONSET_DIR="${TMP_DIR}/DexStar.iconset"
mkdir -p "$ICONSET_DIR"

render_icon() {
  local size="$1"
  sips -z "$size" "$size" "$ICON_PATH" --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
}

render_icon 16
render_icon 32
render_icon 128
render_icon 256
render_icon 512
sips -z 32 32 "$ICON_PATH" --out "${ICONSET_DIR}/icon_16x16@2x.png" >/dev/null
sips -z 64 64 "$ICON_PATH" --out "${ICONSET_DIR}/icon_32x32@2x.png" >/dev/null
sips -z 256 256 "$ICON_PATH" --out "${ICONSET_DIR}/icon_128x128@2x.png" >/dev/null
sips -z 512 512 "$ICON_PATH" --out "${ICONSET_DIR}/icon_256x256@2x.png" >/dev/null
sips -z 1024 1024 "$ICON_PATH" --out "${ICONSET_DIR}/icon_512x512@2x.png" >/dev/null

iconutil -c icns "$ICONSET_DIR" -o "${RESOURCES_DIR}/DexStar.icns"
rm -rf "$TMP_DIR"

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_PATH" >/dev/null 2>&1 || true
touch "$APP_PATH"

if command -v osascript >/dev/null 2>&1; then
  /usr/bin/osascript <<EOF >/dev/null 2>&1 || true
tell application "Finder"
  activate
  set icon of file (POSIX file "$APP_PATH") to icon of file (POSIX file "$ICON_PATH")
end tell
EOF
fi

echo "[完成] 已创建桌面应用快捷方式:"
echo "       $APP_PATH"
echo "[完成] 已使用素材图标:"
echo "       $ICON_PATH"
echo "[提示] 双击 DexStar.app 即可启动。"
