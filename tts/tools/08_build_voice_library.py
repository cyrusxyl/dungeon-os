"""Build the voice library: $BG3_VOICE_HOME/voices/<slug>/<label>.wav + .txt (24 kHz mono, exact ref text).
Source: actors/data/<slug>/refs (made by 07_actor_dataset.py). Existing <slug>/<label>.wav files are skipped; --force overwrites.
Local-only. Run: .venv/bin/python tools/08_build_voice_library.py [--force]"""
import argparse
import csv
from pathlib import Path

import soundfile as sf

from common import H, resample

ROOT = Path(H)
OUT, SR, MIN_S, MAX_S = ROOT / "voices", 24000, 6.0, 10.0


def build(slug, meta, base, force):
    n = 0
    seen = set()
    with open(meta, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            label, text = r["label"].strip(), r["text"].strip()
            src = base / r["path"]
            if not label or label in seen or not text or not src.exists():
                continue
            d = OUT / slug
            if (d / f"{label}.wav").exists() and not force:
                continue
            audio, sr = sf.read(src, dtype="float32", always_2d=True)
            audio = audio.mean(1)
            if sr != SR:
                audio = resample(audio, sr, SR).astype("float32")
            secs = len(audio) / SR
            if not MIN_S <= secs <= MAX_S:
                print(f"  skip {slug}/{label}: {secs:.1f}s outside {MIN_S:.0f}-{MAX_S:.0f}s")
                continue
            seen.add(label)
            d.mkdir(parents=True, exist_ok=True)
            sf.write(d / f"{label}.wav", audio, SR, subtype="PCM_16")
            (d / f"{label}.txt").write_text(text + "\n")
            assert (d / f"{label}.txt").read_text().strip() == text
            assert sf.info(d / f"{label}.wav").samplerate == SR
            n += 1
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing clips")
    force = ap.parse_args().force
    for refs in sorted((ROOT / "actors/data").glob("*/refs")):
        slug, meta = refs.parent.name, refs / "metadata.tsv"
        if not meta.exists():
            print(f"{slug}: no metadata.tsv, skipped")
            continue
        print(f"{slug}: {build(slug, meta, refs.parent, force)} refs")
