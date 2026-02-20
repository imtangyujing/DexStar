from apps.worker.naming_ai import (
    build_final_filename,
    extract_bpm_from_title,
    extract_type_beat_name_from_title,
    normalize_musical_key,
    sanitize_type_beat_name,
)


def test_sanitize_type_beat_name():
    assert sanitize_type_beat_name(" King*Von/Type Beat!! ") == "KingVonType Beat"


def test_normalize_musical_key():
    assert normalize_musical_key("Cm") == "Cm"
    assert normalize_musical_key("F#") == "F#"
    assert normalize_musical_key("???") is None


def test_build_final_filename():
    name = build_final_filename("KingVon", 140, "Cm")
    assert name == "KingVon_140BPM_Cm.mp3"


def test_build_final_filename_without_bpm_or_key():
    name = build_final_filename("Unknown", None, None)
    assert name == "Unknown.mp3"


def test_extract_type_beat_name_from_title():
    title = "FREE King Von x Lil Durk Type Beat 2026 | Prod By XXX"
    assert extract_type_beat_name_from_title(title) == "Durk"


def test_extract_type_beat_name_uses_nearest_word():
    title = "Drake x Travis x Future Type Beat"
    assert extract_type_beat_name_from_title(title) == "Future"


def test_extract_name_from_beat_keyword():
    title = "Metro x Future Beat"
    assert extract_type_beat_name_from_title(title) == "Future"


def test_extract_name_from_chinese_with_english_type_beat():
    title = "周杰伦 Type Beat"
    assert extract_type_beat_name_from_title(title) == "周杰伦"


def test_extract_name_from_chinese_with_english_beat():
    title = "周杰伦 beat"
    assert extract_type_beat_name_from_title(title) == "周杰伦"


def test_extract_name_from_chinese_banzou_keyword():
    title = "周杰伦 风格 伴奏"
    assert extract_type_beat_name_from_title(title) == "周杰伦"


def test_extract_type_beat_name_from_title_not_found():
    assert extract_type_beat_name_from_title("Ambient instrumental") == ""


def test_extract_bpm_from_title():
    assert extract_bpm_from_title("Regalia Type Beat 96 BPM") == 96
    assert extract_bpm_from_title("BPM: 140 Dark Beat") == 140
    assert extract_bpm_from_title("FREE TYPE BEAT 2026") is None
