from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from apps.worker.analysis import AudioAnalysisError, analyze_bpm_and_key
from apps.worker.media import (
    DownloadError,
    download_source,
    embed_cover_art,
    transcode_audio,
    write_mp3_source_metadata,
)
from apps.worker.naming_ai import build_final_filename, extract_type_beat_name_from_title, generate_type_beat_name
from libs.common.config import get_settings
from libs.common.enums import AudioFormat
from libs.common.url_utils import detect_source_site


class DesktopDependencyError(RuntimeError):
    pass


class DesktopDownloadError(RuntimeError):
    pass


@dataclass
class DesktopDownloadResult:
    file_path: Path
    output_dir: Path
    final_filename: str
    type_name: str
    bpm: int | None
    source_title: str
    uploader: str
    has_cover: bool
    cover_status: str
    analysis_error_code: str | None
    analysis_error_message: str | None


def ensure_required_binaries() -> None:
    missing = [name for name in ("yt-dlp", "ffmpeg") if shutil.which(name) is None]
    if missing:
        names = ", ".join(missing)
        raise DesktopDependencyError(f"缺少依赖: {names}")


def normalize_output_dir(output_dir: str | Path | None = None) -> Path:
    target = Path(output_dir).expanduser() if output_dir else Path.home() / "Downloads"
    target.mkdir(parents=True, exist_ok=True)
    return target


def build_download_command(url: str, output_dir: Path) -> list[str]:
    detect_source_site(url)
    output_template = str(output_dir / "%(title)s.%(ext)s")
    return [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--no-playlist",
        "-o",
        output_template,
        url,
    ]


def download_mp3(
    url: str,
    output_dir: str | Path | None = None,
    on_output: Callable[[str], None] | None = None,
) -> DesktopDownloadResult:
    ensure_required_binaries()
    source_site = detect_source_site(url)
    settings = get_settings()
    target_dir = normalize_output_dir(output_dir)

    def emit(message: str) -> None:
        if on_output and message:
            on_output(message)

    with tempfile.TemporaryDirectory(prefix="grab-desktop-") as tmp:
        workdir = Path(tmp)
        try:
            emit("步骤 1/5：下载源音频与封面...")
            artifacts = download_source(url, str(workdir))

            emit("步骤 2/5：转码为最高质量 MP3...")
            output_file = transcode_audio(artifacts.source_file, AudioFormat.mp3, str(workdir))

            emit("步骤 3/5：分析 BPM 并生成命名...")
            final_filename, type_name, bpm, analysis_error_code, analysis_error_message = _analyze_and_name(
                output_file=output_file,
                source_title=artifacts.source_title,
                uploader=artifacts.uploader,
                source_site=source_site.value,
                on_output=emit,
            )

            cover_status = "not_found"
            has_cover = False
            if artifacts.cover_file:
                try:
                    emit("步骤 4/5：嵌入封面（居中 1:1）...")
                    output_file = embed_cover_art(output_file, artifacts.cover_file, str(workdir))
                    cover_status = "embedded"
                    has_cover = True
                except Exception as exc:  # best effort
                    cover_status = "failed"
                    emit(f"封面嵌入失败（已降级）：{str(exc)[:200]}")

            emit("步骤 5/5：写入来源信息并保存文件...")
            try:
                output_file = write_mp3_source_metadata(
                    output_file,
                    source_url=url,
                    artist=artifacts.uploader,
                    advice=settings.copyright_advice_text,
                )
            except Exception as exc:  # best effort
                emit(f"写入 MP3 元数据失败（已降级）：{str(exc)[:200]}")

            final_path = _resolve_final_path(target_dir / final_filename)
            shutil.copy2(output_file, final_path)
            return DesktopDownloadResult(
                file_path=final_path,
                output_dir=target_dir,
                final_filename=final_path.name,
                type_name=type_name,
                bpm=bpm,
                source_title=artifacts.source_title,
                uploader=artifacts.uploader,
                has_cover=has_cover,
                cover_status=cover_status,
                analysis_error_code=analysis_error_code,
                analysis_error_message=analysis_error_message,
            )
        except DownloadError as exc:
            raise DesktopDownloadError(str(exc) or "下载失败，请检查链接或稍后重试。") from exc
        except Exception as exc:  # pragma: no cover
            raise DesktopDownloadError(str(exc) or "下载失败，请检查链接或稍后重试。") from exc


def _analyze_and_name(
    output_file: str,
    source_title: str,
    uploader: str,
    source_site: str,
    on_output: Callable[[str], None] | None = None,
) -> tuple[str, str, int | None, str | None, str | None]:
    settings = get_settings()
    # Desktop mode: lock BPM analysis to TempoCNN.
    bpm_backend = "tempo_cnn_vote"

    bpm_value = 0.0
    analysis_error_code = None
    analysis_error_message = None

    if settings.enable_bpm_key_analysis:
        try:
            analysis = analyze_bpm_and_key(
                output_file,
                bpm_backend_override=bpm_backend,
                key_backend_override="none",
            )
            bpm_value = analysis.bpm
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(exc, AudioAnalysisError):
                code = exc.code
            analysis_error_code = code or "ANALYSIS_FAILED"
            analysis_error_message = str(exc)[:800]
            if analysis_error_code == "ANALYSIS_ENGINE_MISSING":
                bpm_fallback = _analyze_bpm_with_librosa(output_file)
                if bpm_fallback > 0:
                    bpm_value = bpm_fallback
                    analysis_error_code = None
                    analysis_error_message = None
                    if on_output:
                        on_output("BPM 引擎不可用，已切换到兼容算法。")

    rounded_bpm = int(round(bpm_value)) if bpm_value > 0 else None
    type_name = extract_type_beat_name_from_title(source_title)
    if not type_name and settings.enable_ai_naming_fallback:
        try:
            type_name, _model_name = generate_type_beat_name(
                source_title=source_title,
                uploader=uploader,
                bpm=rounded_bpm or 0,
                musical_key="",
                source_site=source_site,
            )
        except Exception as exc:
            if not analysis_error_code:
                analysis_error_code = getattr(exc, "code", None) or "AI_NAME_FAILED"
                analysis_error_message = str(exc)[:800]

    if not type_name:
        type_name = "Unknown"
        if not analysis_error_code:
            analysis_error_code = "TITLE_NAME_NOT_FOUND"
            analysis_error_message = "title naming rule not matched"

    final_filename = build_final_filename(type_name, rounded_bpm, None)
    return final_filename, type_name, rounded_bpm, analysis_error_code, analysis_error_message


def _resolve_final_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise DesktopDownloadError("输出目录里同名文件过多，请清理后重试。")


def _analyze_bpm_with_librosa(audio_file: str) -> float:
    try:
        import librosa  # type: ignore
    except Exception:
        return 0.0

    try:
        y, sr = librosa.load(audio_file, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        value = float(tempo if tempo else 0.0)
    except Exception:
        return 0.0

    if not math.isfinite(value) or value <= 0:
        return 0.0
    while value < 70:
        value *= 2
    while value > 220:
        value /= 2
    return float(value)
