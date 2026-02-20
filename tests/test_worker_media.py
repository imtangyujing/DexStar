from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.worker.media import DownloadError, embed_cover_art, resolve_downloaded_files, write_mp3_source_metadata


def test_resolve_downloaded_files_with_cover(tmp_path: Path):
    (tmp_path / 'source.webm').write_text('x')
    (tmp_path / 'source.jpg').write_text('y')
    artifacts = resolve_downloaded_files(str(tmp_path))
    assert artifacts.source_file.endswith('source.webm')
    assert artifacts.cover_file and artifacts.cover_file.endswith('source.jpg')
    assert artifacts.source_title == ''
    assert artifacts.uploader == 'unknown'


def test_resolve_downloaded_files_without_source(tmp_path: Path):
    (tmp_path / 'source.jpg').write_text('y')
    with pytest.raises(DownloadError):
        resolve_downloaded_files(str(tmp_path))


def test_resolve_downloaded_files_with_info_json(tmp_path: Path):
    (tmp_path / 'source.webm').write_text('x')
    (tmp_path / 'source.info.json').write_text('{"title":"My Beat","uploader":"Beatmaker"}')
    artifacts = resolve_downloaded_files(str(tmp_path), source_url='https://www.youtube.com/watch?v=abc')
    assert artifacts.source_title == 'My Beat'
    assert artifacts.uploader == 'Beatmaker'


def test_embed_cover_art_success(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr('apps.worker.media.subprocess.run', fake_run)
    output = embed_cover_art('output.mp3', 'source.jpg', str(tmp_path))
    assert output.endswith('output_with_cover.mp3')
    assert len(calls) == 2
    assert "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2'" in calls[0]
    assert '-metadata:s:v' in calls[1]


def test_embed_cover_art_failed(monkeypatch, tmp_path: Path):
    def fake_run(_cmd, capture_output, text):
        return SimpleNamespace(returncode=1, stderr='ffmpeg broken')

    monkeypatch.setattr('apps.worker.media.subprocess.run', fake_run)
    with pytest.raises(DownloadError):
        embed_cover_art('output.mp3', 'source.jpg', str(tmp_path))


def test_write_mp3_source_metadata(monkeypatch):
    captured = {'added': []}

    class FakeNoHeader(Exception):
        pass

    class FakeTags:
        def delall(self, _name):
            return None

        def add(self, frame):
            captured['added'].append(frame)

        def save(self, filename, v2_version):
            captured['save'] = (filename, v2_version)

    class Frame(dict):
        pass

    def fake_loader():
        def make_frame(**kwargs):
            return Frame(kwargs)

        return (
            make_frame,  # COMM
            lambda *_args: FakeTags(),  # ID3
            FakeNoHeader,  # ID3NoHeaderError
            make_frame,  # TPE1
            make_frame,  # TXXX
        )

    monkeypatch.setattr('apps.worker.media._load_mutagen_id3', fake_loader)
    out = write_mp3_source_metadata(
        'output.mp3',
        source_url='https://www.youtube.com/watch?v=abc',
        artist='BeatmakerA',
        advice='Respect copyright',
    )
    assert out == 'output.mp3'
    assert captured['save'] == ('output.mp3', 3)
    texts = [str(item.get('text')) for item in captured['added']]
    assert "https://www.youtube.com/watch?v=abc" in ''.join(texts)
    assert "BeatmakerA" in ''.join(texts)
    assert "Respect copyright" in ''.join(texts)
