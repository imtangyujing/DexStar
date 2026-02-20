from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.worker.analysis import AudioAnalysisError
from desktop.core import DesktopDependencyError, build_download_command, download_mp3, ensure_required_binaries, normalize_output_dir
from libs.common.url_utils import UnsupportedUrlError


def test_build_download_command_for_youtube(tmp_path: Path):
    cmd = build_download_command("https://www.youtube.com/watch?v=abc", tmp_path)
    assert cmd[0] == "yt-dlp"
    assert "--audio-format" in cmd
    assert "mp3" in cmd
    assert cmd[-1] == "https://www.youtube.com/watch?v=abc"


def test_build_download_command_rejects_unsupported_domain(tmp_path: Path):
    with pytest.raises(UnsupportedUrlError):
        build_download_command("https://example.com/video", tmp_path)


def test_ensure_required_binaries(monkeypatch):
    def fake_which(name: str):
        return "/usr/local/bin/tool" if name == "yt-dlp" else None

    monkeypatch.setattr("desktop.core.shutil.which", fake_which)
    with pytest.raises(DesktopDependencyError):
        ensure_required_binaries()


def test_normalize_output_dir_creates_dir(tmp_path: Path):
    target = normalize_output_dir(tmp_path / "a" / "b")
    assert target.exists()
    assert target.is_dir()


def test_download_mp3_syncs_web_pipeline_features(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "source.webm"
    cover_file = tmp_path / "cover.jpg"
    output_mp3 = tmp_path / "output.mp3"
    output_with_cover = tmp_path / "output_with_cover.mp3"
    output_with_metadata = tmp_path / "output_with_metadata.mp3"
    for file in (source_file, cover_file, output_mp3, output_with_cover, output_with_metadata):
        file.write_bytes(b"test")

    monkeypatch.setattr("desktop.core.ensure_required_binaries", lambda: None)
    monkeypatch.setattr(
        "desktop.core.get_settings",
        lambda: SimpleNamespace(
            analysis_bpm_backend="auto",
            enable_bpm_key_analysis=True,
            enable_ai_naming_fallback=False,
            copyright_advice_text="advice",
        ),
    )
    monkeypatch.setattr(
        "desktop.core.download_source",
        lambda _url, _workdir: SimpleNamespace(
            source_file=str(source_file),
            cover_file=str(cover_file),
            source_title="regalia type beat",
            uploader="regalia",
        ),
    )
    monkeypatch.setattr("desktop.core.transcode_audio", lambda *_args, **_kwargs: str(output_mp3))
    monkeypatch.setattr(
        "desktop.core.analyze_bpm_and_key",
        lambda *_args, **_kwargs: SimpleNamespace(bpm=96.4, musical_key=""),
    )
    monkeypatch.setattr("desktop.core.extract_type_beat_name_from_title", lambda _title: "Regalia")
    monkeypatch.setattr("desktop.core.embed_cover_art", lambda *_args, **_kwargs: str(output_with_cover))
    monkeypatch.setattr("desktop.core.write_mp3_source_metadata", lambda *_args, **_kwargs: str(output_with_metadata))

    result = download_mp3("https://www.youtube.com/watch?v=abc", output_dir=tmp_path)

    assert result.final_filename == "Regalia_96BPM.mp3"
    assert result.file_path.exists()
    assert result.file_path.name == "Regalia_96BPM.mp3"
    assert result.type_name == "Regalia"
    assert result.bpm == 96
    assert result.has_cover is True
    assert result.cover_status == "embedded"
    assert result.analysis_error_code is None


def test_download_mp3_analysis_failure_uses_unknown_name(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "source.webm"
    output_mp3 = tmp_path / "output.mp3"
    source_file.write_bytes(b"test")
    output_mp3.write_bytes(b"test")

    monkeypatch.setattr("desktop.core.ensure_required_binaries", lambda: None)
    monkeypatch.setattr(
        "desktop.core.get_settings",
        lambda: SimpleNamespace(
            analysis_bpm_backend="auto",
            enable_bpm_key_analysis=True,
            enable_ai_naming_fallback=False,
            copyright_advice_text="advice",
        ),
    )
    monkeypatch.setattr(
        "desktop.core.download_source",
        lambda _url, _workdir: SimpleNamespace(
            source_file=str(source_file),
            cover_file=None,
            source_title="no naming pattern",
            uploader="unknown",
        ),
    )
    monkeypatch.setattr("desktop.core.transcode_audio", lambda *_args, **_kwargs: str(output_mp3))
    monkeypatch.setattr(
        "desktop.core.analyze_bpm_and_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AudioAnalysisError("analysis unavailable")),
    )
    monkeypatch.setattr("desktop.core.extract_type_beat_name_from_title", lambda _title: "")
    monkeypatch.setattr("desktop.core.write_mp3_source_metadata", lambda *_args, **_kwargs: str(output_mp3))

    result = download_mp3("https://www.bilibili.com/video/BV1xx", output_dir=tmp_path)

    assert result.final_filename == "Unknown.mp3"
    assert result.file_path.exists()
    assert result.bpm is None
    assert result.type_name == "Unknown"
    assert result.has_cover is False
    assert result.cover_status == "not_found"
    assert result.analysis_error_code == "ANALYSIS_FAILED"


def test_download_mp3_fallback_to_librosa_when_engine_missing(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "source.webm"
    output_mp3 = tmp_path / "output.mp3"
    source_file.write_bytes(b"test")
    output_mp3.write_bytes(b"test")

    monkeypatch.setattr("desktop.core.ensure_required_binaries", lambda: None)
    monkeypatch.setattr(
        "desktop.core.get_settings",
        lambda: SimpleNamespace(
            analysis_bpm_backend="auto",
            enable_bpm_key_analysis=True,
            enable_ai_naming_fallback=False,
            copyright_advice_text="advice",
        ),
    )
    monkeypatch.setattr(
        "desktop.core.download_source",
        lambda _url, _workdir: SimpleNamespace(
            source_file=str(source_file),
            cover_file=None,
            source_title="regalia type beat",
            uploader="unknown",
        ),
    )
    monkeypatch.setattr("desktop.core.transcode_audio", lambda *_args, **_kwargs: str(output_mp3))
    monkeypatch.setattr(
        "desktop.core.analyze_bpm_and_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError("essentia is not available", code="ANALYSIS_ENGINE_MISSING")
        ),
    )
    monkeypatch.setattr("desktop.core._analyze_bpm_with_librosa", lambda _audio_file: 88.1)
    monkeypatch.setattr("desktop.core.extract_type_beat_name_from_title", lambda _title: "Regalia")
    monkeypatch.setattr("desktop.core.write_mp3_source_metadata", lambda *_args, **_kwargs: str(output_mp3))

    result = download_mp3("https://www.youtube.com/watch?v=abc", output_dir=tmp_path)

    assert result.final_filename == "Regalia_88BPM.mp3"
    assert result.bpm == 88
    assert result.analysis_error_code is None


def test_download_mp3_prefers_tempo_cnn_backend(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "source.webm"
    output_mp3 = tmp_path / "output.mp3"
    source_file.write_bytes(b"test")
    output_mp3.write_bytes(b"test")

    calls: dict[str, str] = {}

    monkeypatch.setattr("desktop.core.ensure_required_binaries", lambda: None)
    monkeypatch.setattr(
        "desktop.core.get_settings",
        lambda: SimpleNamespace(
            analysis_bpm_backend="essentia",
            enable_bpm_key_analysis=True,
            enable_ai_naming_fallback=False,
            copyright_advice_text="advice",
        ),
    )
    monkeypatch.setattr(
        "desktop.core.download_source",
        lambda _url, _workdir: SimpleNamespace(
            source_file=str(source_file),
            cover_file=None,
            source_title="regalia type beat",
            uploader="unknown",
        ),
    )
    monkeypatch.setattr("desktop.core.transcode_audio", lambda *_args, **_kwargs: str(output_mp3))

    def fake_analyze(_audio_file, bpm_backend_override=None, key_backend_override=None):
        calls["bpm_backend_override"] = bpm_backend_override
        calls["key_backend_override"] = key_backend_override
        return SimpleNamespace(bpm=100.2, musical_key="")

    monkeypatch.setattr("desktop.core.analyze_bpm_and_key", fake_analyze)
    monkeypatch.setattr("desktop.core.extract_type_beat_name_from_title", lambda _title: "Regalia")
    monkeypatch.setattr("desktop.core.write_mp3_source_metadata", lambda *_args, **_kwargs: str(output_mp3))

    result = download_mp3("https://www.youtube.com/watch?v=abc", output_dir=tmp_path)

    assert result.final_filename == "Regalia_100BPM.mp3"
    assert calls["bpm_backend_override"] == "tempo_cnn_vote"
    assert calls["key_backend_override"] == "none"
