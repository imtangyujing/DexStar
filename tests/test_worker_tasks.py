from apps.worker.analysis import AudioAnalysisError
from apps.worker.tasks import _run_analysis
from libs.common.db import DownloadJob, JobAIInsight


def _make_job() -> DownloadJob:
    return DownloadJob(
        id='job-test-1',
        user_id='user-test-1',
        source_url='https://www.youtube.com/watch?v=test',
        source_site='youtube',
        format='mp3',
        quality='best',
        status='analyzing',
        progress=65,
    )


def _make_insight() -> JobAIInsight:
    return JobAIInsight(
        job_id='job-test-1',
        has_cover=False,
        cover_status='pending',
        analysis_status='analyzing',
        analysis_mode='standard',
        model_provider='rule',
        model_name='title_rule',
    )


def test_run_analysis_keeps_title_naming_when_audio_analysis_fails(monkeypatch):
    job = _make_job()
    insight = _make_insight()

    def raise_analysis_error(_path: str):
        raise AudioAnalysisError('librosa missing', code='ANALYSIS_ENGINE_MISSING')

    def fake_analyze(path: str, bpm_backend_override=None, key_backend_override=None):
        return raise_analysis_error(path)

    monkeypatch.setattr('apps.worker.tasks.analyze_bpm_and_key', fake_analyze)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_ai_naming_fallback', False, raising=False)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_bpm_key_analysis', True, raising=False)

    filename = _run_analysis(
        job=job,
        insight=insight,
        output_file='/tmp/dummy.mp3',
        source_title='Drake x Future Type Beat',
        uploader='tester',
    )

    assert filename == 'Future.mp3'
    assert insight.analysis_status == 'completed'
    assert insight.type_beat_name == 'Future'
    assert insight.bpm is None
    assert insight.musical_key is None
    assert insight.analysis_error_code == 'ANALYSIS_ENGINE_MISSING'


def test_run_analysis_falls_back_to_unknown_without_bpm_or_key(monkeypatch):
    job = _make_job()
    insight = _make_insight()

    def raise_analysis_error(_path: str):
        raise AudioAnalysisError('librosa missing', code='ANALYSIS_ENGINE_MISSING')

    def fake_analyze(path: str, bpm_backend_override=None, key_backend_override=None):
        return raise_analysis_error(path)

    monkeypatch.setattr('apps.worker.tasks.analyze_bpm_and_key', fake_analyze)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_ai_naming_fallback', False, raising=False)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_bpm_key_analysis', True, raising=False)

    filename = _run_analysis(
        job=job,
        insight=insight,
        output_file='/tmp/dummy.mp3',
        source_title='Ambient Instrumental',
        uploader='tester',
    )

    assert filename == 'Unknown.mp3'
    assert insight.analysis_status == 'completed'
    assert insight.type_beat_name == 'Unknown'
    assert insight.bpm is None
    assert insight.musical_key is None
    assert insight.analysis_error_code == 'ANALYSIS_ENGINE_MISSING'


def test_run_analysis_keeps_bpm_from_essentia(monkeypatch):
    job = _make_job()
    insight = _make_insight()

    class _AudioResult:
        bpm = 166.6
        musical_key = None

    monkeypatch.setattr(
        'apps.worker.tasks.analyze_bpm_and_key',
        lambda _path, bpm_backend_override=None, key_backend_override=None: _AudioResult(),
    )
    monkeypatch.setattr('apps.worker.tasks.settings.enable_ai_naming_fallback', False, raising=False)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_bpm_key_analysis', True, raising=False)

    filename = _run_analysis(
        job=job,
        insight=insight,
        output_file='/tmp/dummy.mp3',
        source_title='Regalia Type Beat 96 BPM',
        uploader='tester',
    )

    assert filename == 'Regalia_167BPM.mp3'
    assert insight.analysis_status == 'completed'
    assert insight.type_beat_name == 'Regalia'
    assert insight.bpm == 166.6
    assert insight.musical_key is None


def test_run_analysis_uses_experimental_bpm_backend(monkeypatch):
    job = _make_job()
    insight = _make_insight()
    insight.analysis_mode = 'experimental'
    called = {}

    class _AudioResult:
        bpm = 98.0
        musical_key = 'Cm'

    def fake_analyze(_path: str, bpm_backend_override=None, key_backend_override=None):
        called['bpm_backend_override'] = bpm_backend_override
        called['key_backend_override'] = key_backend_override
        return _AudioResult()

    monkeypatch.setattr('apps.worker.tasks.analyze_bpm_and_key', fake_analyze)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_ai_naming_fallback', False, raising=False)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_bpm_key_analysis', True, raising=False)

    filename = _run_analysis(
        job=job,
        insight=insight,
        output_file='/tmp/dummy.mp3',
        source_title='Regalia Type Beat',
        uploader='tester',
    )

    assert filename == 'Regalia_98BPM.mp3'
    assert called['bpm_backend_override'] == 'tempo_cnn_vote'
    assert called['key_backend_override'] == 'none'


def test_run_analysis_skips_bpm_and_key_when_disabled(monkeypatch):
    job = _make_job()
    insight = _make_insight()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError('analyze_bpm_and_key should not be called when disabled')

    monkeypatch.setattr('apps.worker.tasks.analyze_bpm_and_key', fail_if_called)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_ai_naming_fallback', False, raising=False)
    monkeypatch.setattr('apps.worker.tasks.settings.enable_bpm_key_analysis', False, raising=False)

    filename = _run_analysis(
        job=job,
        insight=insight,
        output_file='/tmp/dummy.mp3',
        source_title='Regalia Type Beat',
        uploader='tester',
    )

    assert filename == 'Regalia.mp3'
    assert insight.bpm is None
    assert insight.musical_key is None
    assert insight.analysis_error_code is None
