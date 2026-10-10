"""Engine interface and loader."""
import os
from typing import Iterator

import numpy as np


class UnknownVoice(KeyError):
    """The voice slug is not in the library."""


class Engine:
    name = "base"
    model_ver = "0"
    sample_rate = 22050
    voices = ["narrator"]

    def library(self) -> dict[str, list[str]]:
        """slug -> labels."""
        return {v: ["neutral"] for v in self.voices}

    def resolve(self, voice: str, style: str | None) -> str:
        """Return the label to use. Unknown label -> neutral. Unknown voice -> UnknownVoice."""
        labels = self.library().get(voice)
        if labels is None:
            raise UnknownVoice(voice)
        return style if style in labels else "neutral"

    def stream(self, text: str, voice: str, style: str | None) -> Iterator[np.ndarray]:
        """Yield int16 mono arrays for one sentence."""
        raise NotImplementedError


def load_engine(name: str | None = None) -> Engine:
    name = name or os.environ.get("TTS_ENGINE", "mock")
    if name == "mock":
        from .engines.mock import MockEngine
        return MockEngine()
    if name == "f5":
        from .engines.f5 import F5Engine
        return F5Engine()
    raise ValueError(f"unknown engine: {name}")
