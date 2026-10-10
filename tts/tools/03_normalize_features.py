"""Keep WER<=0.1 clips; loudness-normalize (-23 LUFS, peak<=-1 dBFS); write 24k/32k copies; compute prosody features.
Out: ~/bg3voice/norm/{24k,32k}/*.wav, ~/bg3voice/kept.tsv (+features)"""
import os, sys, numpy as np, soundfile as sf, librosa, pyloudnorm as pyln
from common import H, resample
from multiprocessing import Pool
for d in ("24k", "32k"): os.makedirs(f"{H}/norm/{d}", exist_ok=True)
def work(r):
    p, t, d, w = r
    n = os.path.basename(p)
    a, sr = sf.read(p, dtype="float64")
    L = pyln.Meter(sr).integrated_loudness(a)
    a = pyln.normalize.loudness(a, L, -23.0)
    pk = np.abs(a).max()
    if pk > 0.89: a *= 0.89 / pk
    a24 = resample(a, sr, 24000); a32 = resample(a, sr, 32000)
    sf.write(f"{H}/norm/24k/{n}", a24, 24000, subtype="PCM_16")
    sf.write(f"{H}/norm/32k/{n}", a32, 32000, subtype="PCM_16")
    # features on 24k
    hop = 240
    rms = librosa.feature.rms(y=a24, frame_length=960, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-6)
    act = db > db.max() - 35
    f0 = librosa.yin(a24.astype(np.float32), fmin=60, fmax=400, sr=24000, frame_length=1440, hop_length=hop)
    m = min(len(f0), len(act)); f0, act2 = f0[:m], act[:m]
    v = f0[act2 & (f0 < 395) & (f0 > 65)]
    lf = np.log2(v) if len(v) > 20 else np.array([7.0, 7.0])
    nw = len(t.split()); sp = max(act.sum() * hop / 24000, 0.3)
    return (p, t, d, w, n, float(np.median(lf)), float(np.std(lf)), float(db[act].mean()), float(db[act].std()), nw / sp, float(1 - act.mean()))
if __name__ == "__main__":
    rows = [l.rstrip("\n").split("\t") for l in open(f"{H}/wer.tsv")]
    rows = [(r[0], r[1], r[2], float(r[3])) for r in rows if float(r[3]) <= 0.1]
    with Pool(8) as pool: res = pool.map(work, rows, chunksize=16)
    with open(f"{H}/kept.tsv", "w") as o:
        o.write("path\ttext\tdur\twer\tname\tf0med\tf0sd\tdb_mean\tdb_sd\trate\tpause\n")
        for r in res: o.write("\t".join(map(str, r)) + "\n")
    print(len(res))
