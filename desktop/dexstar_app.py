from __future__ import annotations

from pathlib import Path

from .app import DesktopBranding, run_app


def get_dexstar_branding(repo_root: Path | None = None) -> DesktopBranding:
    _ = repo_root or Path(__file__).resolve().parents[1]
    return DesktopBranding(
        window_title="DexStar Desktop",
        app_title="DexStar Desktop",
        subtitle="粘贴链接，一键下载最高质量 MP3（桌面版）。",
        cover_image_path=None,
    )


def main() -> None:
    run_app(branding=get_dexstar_branding())


if __name__ == "__main__":
    main()
