"""Mock engine: sine tones, no GPU."""
import hashlib
import time
from typing import Iterator

import numpy as np

from ..engine import Engine


class MockEngine(Engine):
    name = "mock"
    model_ver = "1"
    sample_rate = 22050
    LABELS = ["neutral", "ominous", "wry", "tense", "warm"]

    def __init__(self, chunk_delay: float = 0.0, sec_per_char: float = 0.02, voices=("narrator",)):
        self.voices = list(voices)
        self.chunk_delay = chunk_delay
        self.sec_per_char = sec_per_char
        self.calls: list[str] = []

    def library(self):
        return {v: list(self.LABELS) for v in self.voices}

    def stream(self, text, voice, style) -> Iterator[np.ndarray]:
        self.calls.append(text)
        freq = 200 + hashlib.md5(text.encode()).digest()[0] * 2
        total = int(self.sample_rate * max(0.2, len(text) * self.sec_per_char))
        step = self.sample_rate // 10
        for start in range(0, total, step):
            n = np.arange(start, min(start + step, total))
            wave = 0.3 * np.sin(2 * np.pi * freq * n / self.sample_rate)
            if self.chunk_delay:
                time.sleep(self.chunk_delay)
            yield (wave * 32767).astype(np.int16)
