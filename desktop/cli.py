from __future__ import annotations

import argparse
from pathlib import Path

from libs.common.url_utils import UnsupportedUrlError

from .core import DesktopDependencyError, DesktopDownloadError, download_mp3


def _print_log(line: str) -> None:
    if line:
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="GRAB Desktop CLI: 下载最高质量 MP3")
    parser.add_argument("--url", help="YouTube/B站视频链接")
    parser.add_argument("--out", help="输出目录，默认 ~/Downloads")
    args = parser.parse_args()

    url = (args.url or "").strip()
    if not url:
        url = input("请输入视频链接（YouTube/B站）：").strip()
    if not url:
        print("未输入链接，已退出。")
        return 1

    output_dir = args.out.strip() if args.out else str(Path.home() / "Downloads")
    print(f"保存目录：{output_dir}")
    print("开始下载（固定最高质量 MP3）...")

    try:
        result = download_mp3(url, output_dir=output_dir, on_output=_print_log)
    except UnsupportedUrlError:
        print("错误：仅支持 YouTube/B站链接。")
        return 1
    except DesktopDependencyError as exc:
        print(f"错误：{exc}。请先安装依赖。")
        return 1
    except DesktopDownloadError as exc:
        print(f"错误：{exc}")
        return 1

    bpm_text = f"{result.bpm} BPM" if result.bpm else "-"
    cover_text = "已嵌入" if result.has_cover else ("未找到封面" if result.cover_status == "not_found" else "嵌入失败")
    print("下载完成。")
    print(f"文件：{result.file_path}")
    print(f"命名：{result.type_name} / {bpm_text}")
    print(f"封面：{cover_text}")
    if result.analysis_error_code:
        print(f"分析提示：{result.analysis_error_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
