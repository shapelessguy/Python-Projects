# Mirrors preparePlex/utils.py's full_language_codes -- kept as its own copy
# since this module is meant to stay self-contained (no dependency on
# preparePlex's heavier utils.py and its .env/paramiko/etc. requirements).
FULL_LANGUAGE_CODES = {
    "French": ["fr", "fre", "fra"],
    "Spanish": ["es", "spa"],
    "Korean": ["ko", "kor"],
    "English": ["en", "eng"],
    "German": ["de", "ger", "deu"],
    "Italian": ["it", "ita"],
    "Portuguese": ["pt", "por"],
    "Russian": ["ru", "rus"],
    "Chinese": ["zh", "chi", "zho"],
    "Japanese": ["ja", "jpn"],
    "Arabic": ["ar", "ara"],
    "Dutch": ["nl", "dut", "nld"],
    "Swedish": ["sv", "swe"],
    "Norwegian": ["no", "nor"],
    "Danish": ["da", "dan"],
    "Finnish": ["fi", "fin"],
    "Polish": ["pl", "pol"],
    "Turkish": ["tr", "tur"],
    "Greek": ["el", "gre", "ell"],
    "Czech": ["cs", "cze", "ces"],
    "Hungarian": ["hu", "hun"],
    "Hebrew": ["he", "heb"],
    "Romanian": ["ro", "rum", "ron"],
    "Ukrainian": ["uk", "ukr"],
    "Thai": ["th", "tha"],
    "Persian": ["fa", "per", "fas"],
    "Kurdish": ["ku", "kur"],
}

_CODE_TO_NAME = {}
for _name, _codes in FULL_LANGUAGE_CODES.items():
    for _code in _codes:
        _CODE_TO_NAME[_code.lower()] = _name
    _CODE_TO_NAME[_name.lower()] = _name


def detect_language_name(raw_value: str | None) -> str | None:
    """Best-effort match of an ffprobe tag value ('ger', 'deu', 'German', ...)
    to one of our known language names. None if not recognized."""
    if not raw_value:
        return None
    return _CODE_TO_NAME.get(raw_value.strip().lower())


def short_code(name: str) -> str:
    """Canonical short code for a language name, used for Whisper's
    `language=` param and the `.gen-{code}.srt` filename suffix."""
    return FULL_LANGUAGE_CODES[name][0]
