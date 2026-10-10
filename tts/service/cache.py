"""On-disk PCM cache: cache/<key>.pcm and cache/<key>.json."""
import hashlib
import json
import os
from pathlib import Path


def make_key(engine: str, model_ver: str, voice: str, style: str | None, sentence: str) -> str:
    raw = "|".join([engine, model_ver, voice, style or "", sentence])
    return hashlib.sha256(raw.encode()).hexdigest()


class Cache:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def has(self, key: str) -> bool:
        return (self.root / f"{key}.pcm").exists()

    def get(self, key: str) -> bytes | None:
        try:
            return (self.root / f"{key}.pcm").read_bytes()
        except FileNotFoundError:
            return None

    def put(self, key: str, pcm: bytes, meta: dict) -> None:
        for ext, data in (("json", json.dumps(meta).encode()), ("pcm", pcm)):
            tmp = self.root / f"{key}.{ext}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, self.root / f"{key}.{ext}")
