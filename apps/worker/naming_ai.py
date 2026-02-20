from __future__ import annotations

import json
import re

import httpx

from libs.common.config import get_settings


class NamingAIError(RuntimeError):
    def __init__(self, message: str, code: str = 'AI_NAME_FAILED'):
        super().__init__(message)
        self.code = code


NOISE_PATTERNS = [
    r'\bfree\b',
    r'\bnon[- ]?profit\b',
    r'\bprod(?:uced)?\s*by\b',
    r'\bofficial\b',
    r'\blyrics?\b',
    r'\bremix\b',
    r'\bdrill\b',
    r'\btrap\b',
]


def extract_type_beat_name_from_title(title: str) -> str:
    raw = title or ''
    lowered = _strip_noise(raw.lower())

    # Example: "king von x durk type beat", "周杰伦 type beat"
    m = re.search(r'([\u4e00-\u9fa5a-z0-9#&/_\- ]{1,48})\s+type\s*beat', lowered, flags=re.I)
    if m:
        return _format_type_name(m.group(1), nearest_only=True)

    # Example: "metro x future beat", "周杰伦 beat"
    m = re.search(r'([\u4e00-\u9fa5a-z0-9#&/_\- ]{1,48})\s+beat\b', lowered, flags=re.I)
    if m:
        candidate = _format_type_name(m.group(1), nearest_only=True)
        if candidate.lower() != 'type':
            return candidate

    # Chinese fallback: "某某风格伴奏" / "某某类型伴奏"
    m = re.search(r'([\u4e00-\u9fa5a-z0-9#&_/\- ]{1,24})(风格|类型)\s*(伴奏|beat)', raw, flags=re.I)
    if m:
        return _format_type_name(m.group(1), nearest_only=True)

    m = re.search(r'([\u4e00-\u9fa5a-z0-9#&_/\- ]{1,24})\s*伴奏', raw, flags=re.I)
    if m:
        return _format_type_name(m.group(1), nearest_only=True)

    return ''


def extract_bpm_from_title(title: str) -> int | None:
    raw = title or ''
    patterns = [
        r'(?<!\d)([6-9]\d|1\d{2}|2[0-2]\d)\s*bpm\b',
        r'\bbpm\s*[:：-]?\s*([6-9]\d|1\d{2}|2[0-2]\d)\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.I)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if 60 <= value <= 220:
            return value
    return None


def _strip_noise(text: str) -> str:
    value = re.sub(r'[\[\]【】()（）{}<>|]', ' ', text)
    value = re.sub(r'[_]+', ' ', value)
    value = re.sub(r'[^\w\s#&/\-]+', ' ', value)
    for pattern in NOISE_PATTERNS:
        value = re.sub(pattern, ' ', value, flags=re.I)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def _format_type_name(name: str, nearest_only: bool = False) -> str:
    parts = re.split(r'[\s/_&-]+', name.strip())
    words = [w for w in parts if w]
    if not words:
        return ''
    if nearest_only:
        words = [words[-1]]
    merged = ''.join(w.capitalize() for w in words)
    return sanitize_type_beat_name(merged)


def generate_type_beat_name(
    source_title: str,
    uploader: str,
    bpm: int,
    musical_key: str,
    source_site: str,
) -> tuple[str, str]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise NamingAIError('OPENAI_API_KEY is missing', code='OPENAI_KEY_MISSING')

    prompt = (
        "你是音乐制作命名助手。请基于输入生成简短 type beat 名称，"
        "只返回 JSON，格式为 {\"type_beat_name\":\"...\"}。"
        "名称使用英文字母数字，可包含空格，不要超过 32 字符。"
    )
    user_input = {
        'source_title': source_title,
        'uploader': uploader,
        'bpm': bpm,
        'musical_key': musical_key,
        'source_site': source_site,
    }
    payload = {
        'model': settings.openai_model,
        'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps(user_input, ensure_ascii=False)},
        ],
        'temperature': 0.3,
    }
    url = settings.openai_base_url.rstrip('/') + '/v1/chat/completions'
    last_error = None
    for _ in range(max(1, settings.ai_max_retries)):
        try:
            with httpx.Client(timeout=float(settings.ai_timeout_seconds)) as client:
                response = client.post(
                    url,
                    headers={
                        'Authorization': f'Bearer {settings.openai_api_key}',
                        'Content-Type': 'application/json',
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                text = data['choices'][0]['message']['content']
                parsed = _parse_json_block(text)
                name = parsed.get('type_beat_name') or ''
                name = sanitize_type_beat_name(name)
                if not name:
                    raise NamingAIError('empty type_beat_name', code='AI_NAME_EMPTY')
                return name, settings.openai_model
        except NamingAIError as exc:
            last_error = exc
        except Exception as exc:  # pragma: no cover
            last_error = NamingAIError(str(exc), code='AI_REQUEST_FAILED')
    assert last_error is not None
    raise last_error


def _parse_json_block(text: str) -> dict:
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.startswith('json'):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, flags=re.S)
        if not match:
            raise NamingAIError('invalid ai json', code='AI_RESPONSE_INVALID')
        try:
            return json.loads(match.group(0))
        except Exception as exc:
            raise NamingAIError('invalid ai json', code='AI_RESPONSE_INVALID') from exc


def sanitize_type_beat_name(name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9\u4e00-\u9fa5 _-]+', '', (name or '').strip())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:32]


def normalize_musical_key(raw_key: str | None) -> str | None:
    key = (raw_key or '').strip()
    if not key:
        return None
    match = re.match(r'^([A-G])([#b]?)(m?)$', key)
    if not match:
        return None
    note, accidental, minor = match.groups()
    return f'{note}{accidental}{minor}'


def build_final_filename(type_beat_name: str, bpm: int | None, musical_key: str | None) -> str:
    safe_type = sanitize_type_beat_name(type_beat_name) or 'Unknown'
    parts = [safe_type]

    if bpm is not None and int(bpm) > 0:
        parts.append(f'{int(bpm)}BPM')
    safe_key = normalize_musical_key(musical_key)
    if safe_key:
        parts.append(safe_key)

    filename = '_'.join(parts) + '.mp3'
    filename = re.sub(r'[^A-Za-z0-9\u4e00-\u9fa5._-]+', '_', filename)
    return filename[:120]
