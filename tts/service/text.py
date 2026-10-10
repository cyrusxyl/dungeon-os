"""Text normalization and sentence splitting."""
import re

_ABBR = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "prof", "mt", "vs", "etc", "capt", "col", "gen", "lt", "sgt", "e.g", "i.e"}
_END = re.compile(r"([.!?…]+)([\"'”’)\]]*)(\s+)")
_START = re.compile(r"[A-Z0-9\"'“‘(\[]")


def normalize(text: str) -> str:
    t = text.replace("*", "").replace("_", "")
    t = re.sub(r"\bDC\s*(\d+)", r"difficulty class \1", t)
    t = re.sub(r"\b(\d*)d(\d+)\b", lambda m: f"{m[1]} dee {m[2]}".strip(), t)
    t = re.sub(r"\bHP\b", "hit points", t)
    t = re.sub(r"(?<![\w])\+(\d)", r"plus \1", t)
    t = re.sub(r"\s*(--+|–)\s*", " — ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    out, last = [], 0
    for m in _END.finditer(text):
        nxt = text[m.end():m.end() + 1]
        if not nxt or not _START.match(nxt):
            continue
        word = re.search(r"([\w.]+)$", text[last:m.start()])
        w = word.group(1).lower() if word else ""
        if m[1] == "." and (w in _ABBR or (len(w) == 1 and w.isalpha() and word.group(1).isupper())):
            continue
        out.append(text[last:m.end(2)].strip())
        last = m.end()
    tail = text[last:].strip()
    if tail:
        out.append(tail)
    return out
