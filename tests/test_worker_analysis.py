import builtins
from types import SimpleNamespace

import pytest

from apps.worker.analysis import (
    AudioAnalysisError,
    _beats_to_bpm,
    _majority_vote_tempo,
    _normalize_bpm_range,
    _normalize_madmom_key_output,
    _normalize_keyfinder_output,
    _normalize_beat_times,
    _resolve_executable,
    analyze_bpm_and_key,
)


def test_analyze_bpm_and_key_rejects_non_essentia_backend(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='librosa',
            analysis_key_backend='librosa',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )
    origin_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {'librosa', 'numpy'}:
            raise ImportError('missing')
        return origin_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    with pytest.raises(AudioAnalysisError) as exc:
        analyze_bpm_and_key('demo.mp3')
    assert exc.value.code == 'ANALYSIS_CONFIG_INVALID'


def test_beats_to_bpm():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    bpm = _beats_to_bpm(beats)
    assert bpm == 120.0


def test_beats_to_bpm_half_time_normalized():
    beats = [0.0, 1.0, 2.0, 3.0]
    bpm = _beats_to_bpm(beats)
    assert bpm == 120.0


def test_normalize_bpm_range():
    assert _normalize_bpm_range(60.0) == 120.0
    assert _normalize_bpm_range(210.0) == 105.0
    assert _normalize_bpm_range(0.0) == 0.0


def test_normalize_beat_times_filters_invalid_values():
    beats = [0.0, '1.0', 'x', float('nan'), 2]
    assert _normalize_beat_times(beats) == [0.0, 1.0, 2.0]


def test_normalize_keyfinder_output():
    assert _normalize_keyfinder_output('Am') == 'Am'
    assert _normalize_keyfinder_output('Bb minor') == 'Bbm'
    assert _normalize_keyfinder_output('F# major') == 'F#'
    assert _normalize_keyfinder_output('not-a-key') == ''


def test_normalize_madmom_key_output():
    assert _normalize_madmom_key_output('C major') == 'C'
    assert _normalize_madmom_key_output('C# minor') == 'C#m'
    assert _normalize_madmom_key_output('A:min') == 'Am'
    assert _normalize_madmom_key_output('Bbmaj') == 'Bb'
    assert _normalize_madmom_key_output('bad-value') == ''


def test_majority_vote_tempo_uses_probability_weighted_bins():
    local_tempos = [120.1, 120.2, 160.0, 160.1]
    local_probs = [0.9, 0.8, 0.2, 0.1]
    assert _majority_vote_tempo(local_tempos, local_probs) == 120.0


def test_auto_backend_uses_essentia_for_key(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )

    monkeypatch.setattr('apps.worker.analysis._analyze_bpm_with_essentia', lambda *_args, **_kwargs: 128.0)
    monkeypatch.setattr('apps.worker.analysis._analyze_key_with_essentia', lambda *_args, **_kwargs: 'Cm')

    result = analyze_bpm_and_key('demo.mp3')
    assert result.bpm == 128.0
    assert result.musical_key == 'Cm'


def test_tempo_cnn_vote_backend_uses_tempo_cnn_result(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='tempo_cnn_vote',
            analysis_key_backend='auto',
            tempo_cnn_graph_path='/opt/grab/models/deeptemp-k16-3.pb',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )

    monkeypatch.setattr('apps.worker.analysis._analyze_bpm_with_tempo_cnn_vote', lambda *_args, **_kwargs: 126.0)
    monkeypatch.setattr('apps.worker.analysis._analyze_key_with_essentia', lambda *_args, **_kwargs: 'Gm')

    result = analyze_bpm_and_key('demo.mp3')
    assert result.bpm == 126.0
    assert result.musical_key == 'Gm'


def test_key_backend_override_uses_madmom(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            tempo_cnn_graph_path='/opt/grab/models/deeptemp-k16-3.pb',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr('apps.worker.analysis._analyze_bpm_with_essentia', lambda *_args, **_kwargs: 110.0)
    monkeypatch.setattr('apps.worker.analysis._analyze_key_with_madmom', lambda *_args, **_kwargs: 'Am')

    result = analyze_bpm_and_key('demo.mp3', key_backend_override='madmom')
    assert result.bpm == 110.0
    assert result.musical_key == 'Am'


def test_key_backend_override_none_skips_key(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            tempo_cnn_graph_path='/opt/grab/models/deeptemp-k16-3.pb',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr('apps.worker.analysis._analyze_bpm_with_essentia', lambda *_args, **_kwargs: 100.0)

    result = analyze_bpm_and_key('demo.mp3', key_backend_override='none')
    assert result.bpm == 100.0
    assert result.musical_key == ''


def test_auto_backend_no_bpm_fallback_when_essentia_missing(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr(
        'apps.worker.analysis._analyze_bpm_with_essentia',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError('essentia missing', code='ANALYSIS_ENGINE_MISSING')
        ),
    )
    monkeypatch.setattr(
        'apps.worker.analysis._analyze_key_with_essentia',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError('essentia missing', code='ANALYSIS_ENGINE_MISSING')
        ),
    )
    with pytest.raises(AudioAnalysisError) as exc:
        analyze_bpm_and_key('demo.mp3')
    assert exc.value.code == 'ANALYSIS_ENGINE_MISSING'


def test_auto_backend_keeps_bpm_when_key_fallback_fails(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )

    monkeypatch.setattr('apps.worker.analysis._analyze_bpm_with_essentia', lambda *_args, **_kwargs: 128.0)
    monkeypatch.setattr(
        'apps.worker.analysis._analyze_key_with_essentia',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError('essentia key missing', code='ANALYSIS_ENGINE_MISSING')
        ),
    )

    result = analyze_bpm_and_key('demo.mp3')
    assert result.bpm == 128.0
    assert result.musical_key == ''


def test_auto_backend_raises_if_both_missing(monkeypatch):
    monkeypatch.setattr(
        'apps.worker.analysis.get_settings',
        lambda: SimpleNamespace(
            analysis_bpm_backend='auto',
            analysis_key_backend='auto',
            keyfinder_cli_bin='keyfinder-cli',
            keyfinder_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr(
        'apps.worker.analysis._analyze_bpm_with_essentia',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError('essentia missing', code='ANALYSIS_ENGINE_MISSING')
        ),
    )
    monkeypatch.setattr(
        'apps.worker.analysis._analyze_key_with_essentia',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AudioAnalysisError('essentia key missing', code='ANALYSIS_ENGINE_MISSING')
        ),
    )

    with pytest.raises(AudioAnalysisError) as exc:
        analyze_bpm_and_key('demo.mp3')
    assert exc.value.code == 'ANALYSIS_ENGINE_MISSING'


def test_resolve_executable_with_extra_candidates(tmp_path):
    tool = tmp_path / 'any_tool'
    tool.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    tool.chmod(0o755)
    found = _resolve_executable('tool-not-found', extra_candidates=[str(tool)])
    assert found == str(tool)


def test_resolve_executable_fallback_when_path_config_is_stale(tmp_path):
    tool = tmp_path / 'any_tool'
    tool.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    tool.chmod(0o755)
    found = _resolve_executable('/opt/old/path/any_tool', extra_candidates=[str(tool)])
    assert found == str(tool)
