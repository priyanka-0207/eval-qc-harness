import re

_WS = re.compile(r"\s+")
_REDACTION = re.compile(r"\bx{2,}\b", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = frozenset(
    "a an and are as at be been but by for from had has have he her his i if in into is it its "
    "me my no not of on or our she so than that the their them then there they this to too was "
    "we were what when which who will with you your".split()
)


def squash(text):
    return _WS.sub(" ", text or "").strip()


def normalize(text):
    text = _REDACTION.sub(" ", (text or "").lower())
    return " ".join(_TOKEN.findall(text))


def tokens(text):
    return [t for t in _TOKEN.findall(_REDACTION.sub(" ", (text or "").lower())) if t not in STOPWORDS]


def sentences(text):
    return [s for s in _SENTENCE.split(squash(text)) if s]


def shingles(text, n=5):
    words = normalize(text).split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def word_count(text):
    return len(squash(text).split())
