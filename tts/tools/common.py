"""Shared helpers for the local-only voice tools. They need the BG3 install."""
import html
import os
import re
import xml.etree.ElementTree as ET
from math import gcd

from scipy.signal import resample_poly

H = os.path.expanduser(os.environ.get("BG3_VOICE_HOME", "~/bg3voice"))
WIN_HOME = os.environ.get("BG3_WIN_HOME", "/mnt/c/bg3voice")  # same folder as seen from WSL
WIN_HOME_WIN = os.environ.get("BG3_WIN_HOME_WIN", r"C:\bg3voice")  # same folder as seen from Windows
LOCA_XML = os.environ.get("BG3_LOCA_XML", f"{WIN_HOME}/loca/english.xml")
DIVINE_EXE = os.environ.get("BG3_DIVINE_EXE", r"C:\bg3voice\tools\Divine.exe")
VOICE_PAK = os.environ.get(
    "BG3_VOICE_PAK",
    r"C:\Program Files (x86)\Steam\steamapps\common\Baldurs Gate 3\Data\Localization\Voice.pak")

_loca = None


def loca() -> dict[str, str]:
    """{contentuid: text} from the BG3 loca xml. Loaded once."""
    global _loca
    if _loca is None:
        _loca = {c.get("contentuid"): c.text or "" for c in ET.parse(LOCA_XML).getroot()}
    return _loca


def clean(t: str) -> str:
    """Loca text -> plain speech text."""
    t = re.sub(r"<br\s*/?>", " ", html.unescape(t))
    t = re.sub(r"<[^>]+>", "", t).replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


def norm(s: str) -> str:
    """Text normalizer for Whisper WER."""
    s = s.lower().replace("’", "'").replace("—", " ").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", s)).strip()


def resample(audio, sr: int, target: int):
    g = gcd(sr, target)
    return resample_poly(audio, target // g, sr // g)
