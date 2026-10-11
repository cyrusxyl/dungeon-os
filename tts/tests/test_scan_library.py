"""Voice library scan: extra refs <label>.2.wav count as the same label. No GPU needed."""
import tempfile
from pathlib import Path

import _path  # noqa: F401
from service.engines.f5 import scan_library

with tempfile.TemporaryDirectory() as t:
    d = Path(t) / "v"
    d.mkdir()
    for n in ("neutral", "angry", "angry.2", "sad.2", "bare"):
        (d / f"{n}.wav").write_bytes(b"")
        if n != "bare":
            (d / f"{n}.txt").write_text("x")
    lib = scan_library(Path(t))
    assert lib == {"v": ["angry", "neutral", "sad"]}, lib
print("ok")
