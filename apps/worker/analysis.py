from __future__ import annotations

from dataclasses import dataclass
import math
import os
import shutil
import statistics
import subprocess
import re
import warnings

from libs.common.config import get_settings


NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Krumhansl templates for major/minor key detection.
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


class AudioAnalysisError(RuntimeError):
    def __init__(self, message: str, code: str = 'ANALYSIS_FAILED'):
        super().__init__(message)
        self.code = code


@dataclass
class AudioAnalysisResult:
    bpm: float
    musical_key: str


def analyze_bpm_and_key(
    audio_file: str,
    bpm_backend_override: str | None = None,
    key_backend_override: str | None = None,
) -> AudioAnalysisResult:
    settings = get_settings()
    bpm_backend = (settings.analysis_bpm_backend or 'auto').lower()
    if bpm_backend_override is not None:
        bpm_backend = (bpm_backend_override or '').lower()
    key_backend = (settings.analysis_key_backend or 'auto').lower()
    if key_backend_override is not None:
        key_backend = (key_backend_override or '').lower()
    if bpm_backend not in {'auto', 'essentia', 'tempo_cnn_vote'}:
        raise AudioAnalysisError(
            f'unsupported bpm backend in strict mode: {bpm_backend}',
            code='ANALYSIS_CONFIG_INVALID',
        )
    if key_backend not in {'auto', 'none', 'essentia', 'madmom'}:
        raise AudioAnalysisError(
            f'unsupported key backend in strict mode: {key_backend}',
            code='ANALYSIS_CONFIG_INVALID',
        )
    if bpm_backend == 'auto':
        bpm_backend = 'essentia'
    if key_backend == 'auto':
        key_backend = 'essentia'

    errors: list[AudioAnalysisError] = []
    bpm_value = 0.0
    key_value = ''

    if bpm_backend == 'essentia':
        try:
            bpm_value = _analyze_bpm_with_essentia(audio_file)
        except AudioAnalysisError as exc:
            errors.append(exc)
    elif bpm_backend == 'tempo_cnn_vote':
        try:
            bpm_value = _analyze_bpm_with_tempo_cnn_vote(audio_file, settings.tempo_cnn_graph_path)
        except AudioAnalysisError as exc:
            errors.append(exc)
    if key_backend == 'none':
        key_value = ''
    elif key_backend == 'essentia':
        try:
            key_value = _analyze_key_with_essentia(audio_file)
        except AudioAnalysisError as exc:
            errors.append(exc)
    elif key_backend == 'madmom':
        try:
            key_value = _analyze_key_with_madmom(audio_file)
        except AudioAnalysisError as exc:
            errors.append(exc)

    if not math.isfinite(bpm_value) or bpm_value <= 0:
        bpm_value = 0.0

    if bpm_value <= 0 and not key_value:
        if errors:
            raise errors[-1]
        raise AudioAnalysisError('analysis unavailable', code='ANALYSIS_FAILED')

    return AudioAnalysisResult(bpm=bpm_value, musical_key=key_value)


def _analyze_bpm_with_btrack(audio_file: str) -> float:
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')
    try:
        import btrack_beat_tracker as btrack  # type: ignore
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('btrack_beat_tracker is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        audio, _sr = librosa.load(audio_file, sr=44100, mono=True)
        if audio is None or len(audio) == 0:
            raise AudioAnalysisError('empty audio for btrack', code='ANALYSIS_BTRACK_FAILED')
        beats = btrack.detect_beats(np.asarray(audio, dtype=np.float32))
        beat_times = _normalize_beat_times(beats)
        bpm = _beats_to_bpm(beat_times)
        if bpm <= 0:
            raise AudioAnalysisError('btrack output has no valid beats', code='ANALYSIS_BTRACK_FAILED')
        return bpm
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_BTRACK_FAILED') from exc


def _analyze_bpm_with_essentia(audio_file: str) -> float:
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')
    try:
        import essentia.standard as es  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('essentia is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        audio = es.MonoLoader(filename=audio_file, sampleRate=44100)()
        if audio is None or len(audio) == 0:
            raise AudioAnalysisError('empty audio for essentia', code='ANALYSIS_ESSENTIA_FAILED')
        bpm, beats, _, _, _ = es.RhythmExtractor2013(method='multifeature')(audio)
        bpm_value = float(bpm) if bpm else 0.0
        beat_times = _normalize_beat_times(beats)
        bpm_from_beats = _beats_to_bpm(beat_times)
        if bpm_from_beats > 0:
            bpm_value = bpm_from_beats
        bpm_value = _normalize_bpm_range(bpm_value)
        if bpm_value <= 0:
            raise AudioAnalysisError('essentia output has no valid tempo', code='ANALYSIS_ESSENTIA_FAILED')
        return bpm_value
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_ESSENTIA_FAILED') from exc


def _analyze_bpm_with_tempo_cnn_vote(audio_file: str, tempo_cnn_graph_path: str) -> float:
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')
    graph_file = (tempo_cnn_graph_path or '').strip()
    if not graph_file or not os.path.exists(graph_file):
        raise AudioAnalysisError('tempo cnn graph file not found', code='ANALYSIS_ENGINE_MISSING')
    try:
        import essentia.standard as es  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('essentia-tensorflow is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        audio = es.MonoLoader(filename=audio_file, sampleRate=44100)()
        if audio is None or len(audio) == 0:
            raise AudioAnalysisError('empty audio for tempo cnn', code='ANALYSIS_TEMPOCNN_FAILED')
        global_tempo, local_tempos, local_probs = es.TempoCNN(graphFilename=graph_file)(audio)
        bpm_value = _majority_vote_tempo(local_tempos, local_probs)
        if bpm_value <= 0:
            bpm_value = _normalize_bpm_range(float(global_tempo) if global_tempo else 0.0)
        if bpm_value <= 0:
            raise AudioAnalysisError('tempo cnn output has no valid tempo', code='ANALYSIS_TEMPOCNN_FAILED')
        return bpm_value
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_TEMPOCNN_FAILED') from exc


def _analyze_key_with_essentia(audio_file: str) -> str:
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')
    try:
        import essentia.standard as es  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('essentia is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        audio = es.MonoLoader(filename=audio_file, sampleRate=44100)()
        if audio is None or len(audio) == 0:
            raise AudioAnalysisError('empty audio for essentia key', code='ANALYSIS_ESSENTIA_FAILED')
        key, scale, _strength = es.KeyExtractor(profileType='edma')(audio)
        note = _normalize_note_token(str(key))
        if not note:
            raise AudioAnalysisError('essentia output has no key', code='ANALYSIS_ESSENTIA_FAILED')
        scale_value = (scale or '').strip().lower()
        if scale_value == 'minor':
            return f'{note}m'
        return note
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_ESSENTIA_FAILED') from exc


def _analyze_key_with_madmom(audio_file: str) -> str:
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')

    try:
        _apply_madmom_py311_compat()
        from madmom.features.key import CNNKeyRecognitionProcessor, key_prediction_to_label  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('madmom is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        processor = CNNKeyRecognitionProcessor()
        prediction = processor(audio_file)
        label = key_prediction_to_label(prediction)
        key = _normalize_madmom_key_output(label)
        if not key:
            raise AudioAnalysisError('madmom output has no key', code='ANALYSIS_MADMOM_FAILED')
        return key
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_MADMOM_FAILED') from exc


def _analyze_key_with_keyfinder_cli(audio_file: str, keyfinder_cli_bin: str, timeout_seconds: int) -> str:
    resolved_bin = _resolve_executable(
        keyfinder_cli_bin,
        extra_candidates=[
            '~/Library/Python/3.11/bin/keyfinder-cli',
            '~/Library/Python/3.11/bin/keyfinder',
            '~/Library/Python/3.9/bin/keyfinder-cli',
            '~/Library/Python/3.9/bin/keyfinder',
        ],
    )
    if not resolved_bin:
        raise AudioAnalysisError(f'{keyfinder_cli_bin} is not available', code='ANALYSIS_ENGINE_MISSING')
    if not os.path.exists(audio_file):
        raise AudioAnalysisError('audio file not found', code='ANALYSIS_FAILED')

    cmd = [resolved_bin, '-n', 'standard', audio_file]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=float(timeout_seconds))
    except subprocess.TimeoutExpired as exc:
        raise AudioAnalysisError('keyfinder timeout', code='ANALYSIS_TIMEOUT') from exc

    if result.returncode != 0:
        message = (result.stderr or result.stdout or 'keyfinder failed').strip()
        raise AudioAnalysisError(message, code='ANALYSIS_KEYFINDER_FAILED')

    output = (result.stdout or '').strip().splitlines()
    if not output:
        raise AudioAnalysisError('keyfinder empty output', code='ANALYSIS_KEYFINDER_FAILED')
    key = _normalize_keyfinder_output(output[-1])
    if not key:
        raise AudioAnalysisError('keyfinder invalid output', code='ANALYSIS_KEYFINDER_FAILED')
    return key


def _analyze_with_librosa(audio_file: str) -> tuple[float, str]:
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('librosa is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        y, sr = librosa.load(audio_file, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo if tempo else 0.0)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        key = detect_key(chroma.mean(axis=1), np)
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_FAILED') from exc

    if not math.isfinite(bpm) or bpm <= 0:
        bpm = 0.0
    return bpm, key


def _analyze_key_with_librosa(audio_file: str) -> str:
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        raise AudioAnalysisError('librosa is not available', code='ANALYSIS_ENGINE_MISSING') from exc

    try:
        y, sr = librosa.load(audio_file, mono=True)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        return detect_key(chroma.mean(axis=1), np)
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(str(exc), code='ANALYSIS_FAILED') from exc


def _normalize_beat_times(beats) -> list[float]:
    out: list[float] = []
    if beats is None:
        return out
    for value in beats:
        try:
            num = float(value)
        except Exception:
            continue
        if math.isfinite(num):
            out.append(num)
    return out


def _majority_vote_tempo(local_tempos, local_probs) -> float:
    vote_buckets: dict[int, float] = {}
    if local_tempos is None:
        return 0.0

    for index, tempo_value in enumerate(local_tempos):
        try:
            tempo = float(tempo_value)
        except Exception:
            continue
        if not math.isfinite(tempo):
            continue
        normalized = _normalize_bpm_range(tempo)
        if normalized <= 0:
            continue

        probability = 1.0
        if local_probs is not None and index < len(local_probs):
            try:
                probability = float(local_probs[index])
            except Exception:
                probability = 1.0
            if not math.isfinite(probability) or probability <= 0:
                probability = 1.0

        bin_bpm = int(round(normalized))
        vote_buckets[bin_bpm] = vote_buckets.get(bin_bpm, 0.0) + probability

    if not vote_buckets:
        return 0.0
    best_bpm, _ = max(vote_buckets.items(), key=lambda item: (item[1], item[0]))
    return float(best_bpm)


def _beats_to_bpm(beats: list[float]) -> float:
    if len(beats) < 2:
        return 0.0
    intervals = [beats[i] - beats[i - 1] for i in range(1, len(beats))]
    intervals = [x for x in intervals if 0.15 <= x <= 2.0]
    if not intervals:
        return 0.0
    beat_interval = statistics.median(intervals)
    return _normalize_bpm_range(60.0 / beat_interval)


def _normalize_bpm_range(bpm: float) -> float:
    value = float(bpm) if math.isfinite(bpm) else 0.0
    if value <= 0:
        return 0.0
    while value < 70:
        value *= 2
    while value > 200:
        value /= 2
    return float(value)


def _normalize_keyfinder_output(text: str) -> str:
    raw = (text or '').strip()
    if not raw:
        return ''
    match = re.search(r'([A-G](#|b)?)\s*(major|minor)', raw, flags=re.I)
    if match:
        note = _normalize_note_token(match.group(1))
        mode = match.group(3).lower()
        if mode == 'minor':
            return f'{note}m'
        return note
    token = _normalize_note_token(raw.split()[0])
    if re.match(r'^[A-G](#|b)?m?$', token):
        return token
    return ''


def _normalize_note_token(token: str) -> str:
    value = (token or '').strip()
    if not value:
        return ''
    if len(value) == 1:
        return value.upper()
    return value[0].upper() + value[1:]


def _normalize_madmom_key_output(label: str) -> str:
    raw = (label or '').strip()
    if not raw:
        return ''

    match = re.search(r'^([A-G](?:#|b)?)\s+(major|minor)$', raw, flags=re.I)
    if match:
        note = _normalize_note_token(match.group(1))
        mode = match.group(2).lower()
        return f'{note}m' if mode == 'minor' else note

    compact = raw.replace(':', '').replace(' ', '')
    match = re.search(r'^([A-G](?:#|b)?)(maj|min|m)$', compact, flags=re.I)
    if match:
        note = _normalize_note_token(match.group(1))
        mode = match.group(2).lower()
        return f'{note}m' if mode in {'min', 'm'} else note

    match = re.search(r'^([A-G](?:#|b)?)(m?)$', compact, flags=re.I)
    if match:
        note = _normalize_note_token(match.group(1))
        suffix = 'm' if match.group(2).lower() == 'm' else ''
        return f'{note}{suffix}'
    return ''


def _apply_madmom_py311_compat() -> None:
    # madmom 0.16 uses collections.MutableSequence and np.float aliases.
    import collections
    import collections.abc
    import numpy as np  # type: ignore

    for attr in ('MutableSequence', 'Sequence', 'MutableMapping', 'Mapping'):
        if not hasattr(collections, attr) and hasattr(collections.abc, attr):
            setattr(collections, attr, getattr(collections.abc, attr))

    alias_map = {
        'float': float,
        'int': int,
        'complex': complex,
        'bool': bool,
        'object': object,
    }
    for alias, value in alias_map.items():
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', FutureWarning)
            exists = hasattr(np, alias)
        if not exists:
            setattr(np, alias, value)


def _resolve_executable(binary: str, extra_candidates: list[str] | None = None) -> str | None:
    if not binary:
        return None
    if os.path.sep in binary:
        path = os.path.expanduser(binary)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        # If a path-style config is stale (e.g. host path in docker),
        # continue to fallback lookup instead of hard-failing.
        binary = os.path.basename(path)

    found = shutil.which(binary)
    if found:
        return found

    for item in extra_candidates or []:
        candidate = os.path.expanduser(item)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def detect_key(chroma_mean, np_module) -> str:
    if len(chroma_mean) != 12:
        raise AudioAnalysisError('invalid chroma size', code='ANALYSIS_INVALID_CHROMA')

    best_score = float('-inf')
    best_key = 'C'
    for i, note in enumerate(NOTES):
        major_profile = np_module.roll(np_module.array(MAJOR_PROFILE), i)
        minor_profile = np_module.roll(np_module.array(MINOR_PROFILE), i)
        major_score = float(np_module.corrcoef(chroma_mean, major_profile)[0, 1])
        minor_score = float(np_module.corrcoef(chroma_mean, minor_profile)[0, 1])
        if major_score > best_score:
            best_score = major_score
            best_key = note
        if minor_score > best_score:
            best_score = minor_score
            best_key = f'{note}m'
    return best_key
