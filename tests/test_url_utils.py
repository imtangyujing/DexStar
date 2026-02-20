import pytest

from libs.common.enums import SourceSite
from libs.common.url_utils import UnsupportedUrlError, detect_source_site


def test_detect_youtube():
    assert detect_source_site('https://www.youtube.com/watch?v=abc') == SourceSite.youtube


def test_detect_bilibili():
    assert detect_source_site('https://www.bilibili.com/video/BV1xx') == SourceSite.bilibili


def test_detect_unsupported():
    with pytest.raises(UnsupportedUrlError):
        detect_source_site('https://example.com/video')
