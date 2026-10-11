"""F5-TTS engine. Needs the `gpu` extra: uv sync --extra gpu"""
import os
import zlib
from pathlib import Path
from typing import Iterator

import numpy as np

from ..engine import Engine, UnknownVoice

BG3_VOICE_HOME = Path(os.environ.get("BG3_VOICE_HOME", "~/bg3voice")).expanduser()
VOICES_DIR = Path(os.environ.get("TTS_VOICES_DIR") or BG3_VOICE_HOME / "voices").expanduser()
CHUNK = 4800  # samples per yielded piece (0.2 s)
NFE_STEP, SWAY, CFG, SEED = 16, -1.0, 2.0, 1  # 16 steps: same WER as 32, 25% faster


def scan_library(root: Path = VOICES_DIR) -> dict[str, list[str]]:
    """slug -> labels that have both <label>.wav and <label>.txt. <label>.2.wav, <label>.3.wav ... are extra refs for the label."""
    lib: dict[str, list[str]] = {}
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            labels = sorted({w.stem.split(".")[0] for w in d.glob("*.wav") if w.with_suffix(".txt").exists()})
            if "neutral" in labels:
                lib[d.name] = labels
    return lib


class F5Engine(Engine):
    name = "f5"
    sample_rate = 24000
    def __init__(self):
        from f5_tts.api import F5TTS

        self.model_ver = f"F5TTS_v1_Base:nfe{NFE_STEP}"
        self.tts = F5TTS(model="F5TTS_v1_Base", device="cuda")
        self._refs: dict[Path, tuple] = {}  # ref wav -> (audio, text)
        self._files: dict[tuple[str, str], list[Path]] = {}  # (slug, label) -> ref wavs
        self._lib: tuple[tuple, dict] | None = None  # (dir signature, library)
        if "narrator" not in self.library():
            raise RuntimeError(f"no narrator voice in {VOICES_DIR}: run tools/08_build_voice_library.py")
        for t in ("Hm.", "Warm up. One, two, three.", "You wake to the sound of dripping water, slow and patient.",
                  "The corridor stretches on, and on, until even your own footsteps seem to belong to someone else."):
            for _ in self.stream(t, "narrator", None):  # warm kernels at several lengths
                pass

    def library(self):
        """Cached scan. Rescan when the voices dir or a voice dir changes."""
        dirs = [VOICES_DIR, *(p for p in VOICES_DIR.glob("*") if p.is_dir())] if VOICES_DIR.is_dir() else []
        sig = max((p.stat().st_mtime_ns for p in dirs), default=0), len(dirs)
        if self._lib is None or self._lib[0] != sig:
            self._lib = (sig, scan_library())
        return self._lib[1]

    def _ref(self, voice: str, label: str, text: str):
        """One reference clip of the label, chosen by the line text, preprocessed on first use.
        Same text, same clip, so the cache stays valid."""
        if (voice, label) not in self._files:
            if label not in self.library().get(voice, ()):
                raise UnknownVoice(voice)
            d = VOICES_DIR / voice
            self._files[voice, label] = [w for w in sorted(d.glob(f"{label}.wav")) + sorted(d.glob(f"{label}.[0-9]*.wav"))
                                         if w.with_suffix(".txt").exists()]
        files = self._files[voice, label]
        wav = files[zlib.crc32(text.encode()) % len(files)]
        if wav not in self._refs:
            import torchaudio
            from f5_tts.infer.utils_infer import preprocess_ref_audio_text

            path, ref_text = preprocess_ref_audio_text(str(wav), wav.with_suffix(".txt").read_text().strip(), show_info=lambda *a: None)
            audio, sr = torchaudio.load(path)
            self._refs[wav] = ((audio.mean(0, keepdim=True), sr), ref_text)
        return self._refs[wav]

    def stream(self, text, voice, style) -> Iterator[np.ndarray]:
        from f5_tts.infer.utils_infer import chunk_text, infer_batch_process
        from f5_tts.model.utils import seed_everything

        label = style if style in self.library().get(voice, ()) else "neutral"
        ref, ref_text = self._ref(voice, label, text)
        audio, sr = ref
        secs = audio.shape[-1] / sr
        max_chars = int(len(ref_text.encode()) / secs * (22 - secs))
        batches = chunk_text(text, max_chars=max_chars)
        if not batches:
            return
        seed_everything(SEED)
        gen = infer_batch_process(
            ref, ref_text, batches, self.tts.ema_model, self.tts.vocoder,
            mel_spec_type=self.tts.mel_spec_type, progress=None, nfe_step=NFE_STEP,
            cfg_strength=CFG, sway_sampling_coef=SWAY, device=self.tts.device,
            streaming=True, chunk_size=CHUNK)
        for wave, _sr in gen:
            yield (np.clip(wave, -1, 1) * 32767).astype(np.int16)
