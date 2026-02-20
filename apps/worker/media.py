from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
import json
from pathlib import Path

from libs.common.enums import AudioFormat, ErrorCode


class DownloadError(RuntimeError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.download_failed):
        super().__init__(message)
        self.code = code


@dataclass
class DownloadArtifacts:
    source_file: str
    cover_file: str | None
    source_title: str
    uploader: str


IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}
META_SUFFIXES = {'.json'}


def run_cmd(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or '').lower()
        if 'login' in stderr or '会员' in stderr or 'restricted' in stderr:
            raise DownloadError(result.stderr.strip(), ErrorCode.source_restricted)
        raise DownloadError(result.stderr.strip() or 'command failed', ErrorCode.download_failed)


def download_source(url: str, workdir: str) -> DownloadArtifacts:
    Path(workdir).mkdir(parents=True, exist_ok=True)
    source_path = os.path.join(workdir, 'source.%(ext)s')
    cmd = [
        'yt-dlp',
        '-f',
        'bestaudio/best',
        '-o',
        source_path,
        '--write-thumbnail',
        '--convert-thumbnails',
        'jpg',
        '--write-info-json',
        '--no-playlist',
        url,
    ]
    run_cmd(cmd)
    return resolve_downloaded_files(workdir, source_url=url)


def resolve_downloaded_files(workdir: str, source_url: str = '') -> DownloadArtifacts:
    source_file = None
    cover_file = None
    info_file = None
    for item in sorted(Path(workdir).glob('source.*')):
        if not item.is_file() or item.name == 'source.%(ext)s':
            continue
        if item.suffix.lower() in IMAGE_SUFFIXES:
            if cover_file is None:
                cover_file = str(item)
            continue
        if item.suffix.lower() in META_SUFFIXES:
            info_file = str(item)
            continue
        source_file = str(item)
    if not source_file:
        raise DownloadError('source not found')
    title, uploader = extract_metadata(info_file, source_url=source_url)
    return DownloadArtifacts(
        source_file=source_file,
        cover_file=cover_file,
        source_title=title,
        uploader=uploader,
    )


def extract_metadata(info_file: str | None, source_url: str = '') -> tuple[str, str]:
    if not info_file:
        return source_url, 'unknown'
    try:
        with open(info_file, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        title = str(data.get('title') or source_url or '')
        uploader = str(data.get('uploader') or data.get('channel') or 'unknown')
        return title, uploader
    except Exception:
        return source_url, 'unknown'


def transcode_audio(source_file: str, target_format: AudioFormat, output_dir: str) -> str:
    out = Path(output_dir) / f'output.{target_format.value}'
    cmd = ['ffmpeg', '-y', '-i', source_file]
    if target_format == AudioFormat.mp3:
        cmd += ['-codec:a', 'libmp3lame', '-q:a', '0']
    else:
        cmd += ['-acodec', 'pcm_s16le']
    cmd += [str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(result.stderr.strip() or 'ffmpeg failed', ErrorCode.transcode_failed)
    return str(out)


def embed_cover_art(mp3_file: str, cover_file: str, output_dir: str) -> str:
    square_cover_file = crop_cover_to_square(cover_file, output_dir)
    out = Path(output_dir) / 'output_with_cover.mp3'
    cmd = [
        'ffmpeg',
        '-y',
        '-i',
        mp3_file,
        '-i',
        square_cover_file,
        '-map',
        '0:a',
        '-map',
        '1:v',
        '-c:a',
        'copy',
        '-c:v',
        'mjpeg',
        '-id3v2_version',
        '3',
        '-metadata:s:v',
        'title=Album cover',
        '-metadata:s:v',
        'comment=Cover (front)',
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(result.stderr.strip() or 'ffmpeg cover embed failed', ErrorCode.transcode_failed)
    return str(out)


def crop_cover_to_square(cover_file: str, output_dir: str) -> str:
    out = Path(output_dir) / 'cover_square.jpg'
    cmd = [
        'ffmpeg',
        '-y',
        '-i',
        cover_file,
        '-vf',
        "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2'",
        '-frames:v',
        '1',
        '-q:v',
        '2',
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(result.stderr.strip() or 'ffmpeg cover crop failed', ErrorCode.transcode_failed)
    return str(out)


def write_mp3_source_metadata(mp3_file: str, source_url: str, artist: str, advice: str) -> str:
    try:
        COMM, ID3, ID3NoHeaderError, TPE1, TXXX = _load_mutagen_id3()
        try:
            tags = ID3(mp3_file)
        except ID3NoHeaderError:
            tags = ID3()

        tags.delall('COMM')
        tags.delall('TPE1')
        tags.delall('TXXX:Advice')

        tags.add(COMM(encoding=3, lang='eng', desc='source', text=[source_url]))
        tags.add(TPE1(encoding=3, text=[artist or 'Unknown']))
        tags.add(TXXX(encoding=3, desc='Advice', text=[advice]))
        tags.save(mp3_file, v2_version=3)
        return mp3_file
    except Exception as exc:
        raise DownloadError(str(exc) or 'metadata write failed', ErrorCode.transcode_failed) from exc


def _load_mutagen_id3():
    from mutagen.id3 import COMM, ID3, ID3NoHeaderError, TPE1, TXXX

    return COMM, ID3, ID3NoHeaderError, TPE1, TXXX
