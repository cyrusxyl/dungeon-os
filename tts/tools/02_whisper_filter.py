"""Whisper large-v3 as filter vs loca text. Out: ~/bg3voice/wer.tsv (path,text,dur,wer,hyp)"""
import os, jiwer, soundfile as sf
from common import H, norm, resample
from faster_whisper import WhisperModel
rows = [l.rstrip("\n").split("\t") for l in open(f"{H}/candidates.tsv")]
m = WhisperModel("large-v3", device="cuda", compute_type="float16")
done = set()
outp = f"{H}/wer.tsv"
if os.path.exists(outp): done = {l.split("\t")[0] for l in open(outp)}
out = open(outp, "a")
for i, (p, t, d) in enumerate(rows):
    if p in done: continue
    a, sr = sf.read(p, dtype='float32'); a = resample(a, sr, 16000)
    segs, _ = m.transcribe(a.astype('float32'), language="en", beam_size=5, condition_on_previous_text=False)
    hyp = " ".join(s.text for s in segs).strip()
    w = jiwer.wer(norm(t), norm(hyp) or "x")
    out.write(f"{p}\t{t}\t{d}\t{w:.3f}\t{hyp}\n"); out.flush()
    if i % 200 == 0: print(i, flush=True)
