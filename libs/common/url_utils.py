from urllib.parse import urlparse

from libs.common.enums import ErrorCode, SourceSite


class UnsupportedUrlError(ValueError):
    code = ErrorCode.unsupported_url


YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com'}
BILIBILI_HOSTS = {'bilibili.com', 'www.bilibili.com', 'b23.tv'}


def detect_source_site(url: str) -> SourceSite:
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception as exc:  # pragma: no cover
        raise UnsupportedUrlError('invalid url') from exc
    if host in YOUTUBE_HOSTS:
        return SourceSite.youtube
    if host in BILIBILI_HOSTS:
        return SourceSite.bilibili
    raise UnsupportedUrlError('unsupported domain')
