from pathlib import Path

from desktop.dexstar_app import get_dexstar_branding


def test_get_dexstar_branding_uses_expected_title(tmp_path: Path):
    branding = get_dexstar_branding(repo_root=tmp_path)

    assert branding.window_title == "DexStar Desktop"
    assert branding.app_title == "DexStar Desktop"
    assert branding.cover_image_path is None
