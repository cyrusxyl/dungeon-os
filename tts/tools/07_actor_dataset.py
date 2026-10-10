"""Per-actor F5-TTS dataset from BG3: sample, Whisper filter, normalize, split.
Usage: python3 07_actor_dataset.py [slug-or-uuid ...]   (no args = all named actors)
Out: ~/bg3voice/actors/data/<slug>/{refs,train,heldout}/ + metadata.tsv, stats.json; then SUMMARY.md and refs.html.
Needs LD_LIBRARY_PATH from env.sh for Whisper. Audio stays outside the repo."""
import os, re, sys, json, html, shutil, random, subprocess, glob, collections
import numpy as np, pandas as pd, soundfile as sf, librosa, pyloudnorm as pyln, jiwer
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from common import H, WIN_HOME, WIN_HOME_WIN, DIVINE_EXE, VOICE_PAK, loca, clean, norm, resample
A = f"{H}/actors"; D = f"{A}/data"
WORK = os.environ.get("WORK", "/tmp/claude-1000/-home-cyrus-workspace-dungeon-os/3497286c-783e-4523-9297-cef5aedd5dd4/scratchpad/work")
WIN = f"{WIN_HOME}/actors_full"
MAXN, WER_MAX, TRAIN_MIN = 700, 0.1, 30
NONSPEECH = re.compile(r"^(breath|idle|roar|laugh|grunt|scream|cough|sigh|hum|whistle|gasp|groan|death|hit|attack|effort|pain|snore|cry|sob|chuckle)|var\s*\d+$", re.I)
NAMES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "actors.json")
if not os.path.exists(NAMES): NAMES = f"{A}/names.json"  # old location
F = ["f0med", "f0sd", "db_mean", "db_sd", "rate", "pause"]

def slug_of(name):
    m = re.match(r"tav (\d) \((\w)\)", name.lower())
    return f"tav{m[1]}-{m[2]}" if m else re.sub(r"[^a-z0-9]+", "", name.lower())

_by = _model = None
def by_actor():
    global _by
    if _by is None:
        _by = collections.defaultdict(list)
        for line in open(f"{H}/voice_list.txt"):
            m = re.search(r"/v(\w+?)_(h\w+)\.wem\t", line)
            if m: _by[m[1]].append(m[2])
    return _by
def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")  # small VRAM: GPU is shared
    return _model

def sample(u, slug):
    """Extract all wems of the actor, convert a random sample of up to MAXN with valid text and 2-15 s."""
    L = loca(); cand = []
    for h in by_actor()[u]:
        raw = L.get(h)
        if not raw or re.search(r"\[\d+\]", raw): continue
        t = clean(raw)
        if len(t.split()) < 3 or NONSPEECH.search(t): continue
        cand.append((h, t))
    random.Random(0).shuffle(cand)
    extracted = len(cand)
    wd = f"{WIN}/{slug}"; shutil.rmtree(wd, ignore_errors=True)
    subprocess.run(["powershell.exe", "-c", f'{DIVINE_EXE} -g bg3 -a extract-package -s "{VOICE_PAK}" -d {WIN_HOME_WIN}\\{slug} -x "*v{u}_h*.wem"'], capture_output=True)
    src = {os.path.basename(f)[:-4].split("_", 1)[1]: os.path.join(r, f) for r, _, fs in os.walk(wd) for f in fs if f.endswith(".wem")}
    os.makedirs(f"{WORK}/{slug}/wav", exist_ok=True); rows = []
    for h, t in cand:
        if len(rows) >= MAXN: break
        if h not in src: continue
        w = f"{WORK}/{slug}/wav/{h}.wav"
        if not os.path.exists(w): subprocess.run([f"{H}/vgm/vgmstream-cli", "-o", w, src[h]], capture_output=True)
        if not os.path.exists(w): continue
        d = sf.info(w).duration
        if 2 <= d <= 15: rows.append((w, t, d))
    shutil.rmtree(wd, ignore_errors=True)
    return extracted, rows

def whisper(rows, cache):
    done = {}
    if os.path.exists(cache):
        for l in open(cache):
            p = l.rstrip("\n").split("\t"); done[p[0]] = float(p[1])
    out = open(cache, "a"); m = model(); res = []
    for w, t, d in rows:
        if w not in done:
            a, sr = sf.read(w, dtype="float32")
            if a.ndim > 1: a = a.mean(1)
            a = resample(a, sr, 16000).astype("float32")
            segs, _ = m.transcribe(a, language="en", beam_size=5, condition_on_previous_text=False)
            hyp = " ".join(s.text for s in segs).strip()
            done[w] = jiwer.wer(norm(t), norm(hyp) or "x")
            out.write(f"{w}\t{done[w]:.3f}\n"); out.flush()
        res.append((w, t, d, done[w]))
    return res

def feats(r):
    w, t, d, wer, outp = r
    a, sr = sf.read(w, dtype="float64")
    if a.ndim > 1: a = a.mean(1)
    a = pyln.normalize.loudness(a, pyln.Meter(sr).integrated_loudness(a), -23.0)
    pk = np.abs(a).max()
    if pk > 0.89: a *= 0.89 / pk
    a24 = resample(a, sr, 24000)
    sf.write(outp, a24, 24000, subtype="PCM_16")
    hop = 240
    db = 20 * np.log10(librosa.feature.rms(y=a24, frame_length=960, hop_length=hop)[0] + 1e-6)
    act = db > db.max() - 35
    f0 = librosa.yin(a24.astype(np.float32), fmin=60, fmax=400, sr=24000, frame_length=1440, hop_length=hop)
    m = min(len(f0), len(act)); v = f0[:m][act[:m] & (f0[:m] < 395) & (f0[:m] > 65)]
    lf = np.log2(v) if len(v) > 20 else np.array([7.0, 7.0])
    sp = max(act.sum() * hop / 24000, 0.3)
    return (outp, t, len(a24) / 24000, wer, float(np.median(lf)), float(np.std(lf)), float(db[act].mean()), float(db[act].std()), len(t.split()) / sp, float(1 - act.mean()))

def build(u, name, slug):
    od = f"{D}/{slug}"; shutil.rmtree(od, ignore_errors=True)
    nd = f"{WORK}/{slug}/norm"; os.makedirs(nd, exist_ok=True)
    extracted, rows = sample(u, slug)
    wr = whisper(rows, f"{WORK}/{slug}/wer.tsv")
    good = [r for r in wr if r[3] <= WER_MAX]
    from multiprocessing import Pool
    with Pool(6) as p: res = p.map(feats, [(w, t, d, e, f"{nd}/{os.path.basename(w)}") for w, t, d, e in good], chunksize=8)
    df = pd.DataFrame(res, columns=["path", "text", "dur", "wer"] + F)
    X = StandardScaler().fit_transform(df[F]); z = pd.DataFrame(X, columns=F, index=df.index)
    df["cluster"] = KMeans(min(8, len(df)), n_init=10, random_state=0).fit_predict(X)
    rng = np.random.default_rng(0); used = set(); refs = []
    c = df[df.dur.between(6, 10) & (df.wer == 0)].index
    sc = {"neutral": -(z.loc[c].abs().sum(axis=1)),
          "ominous": -z.loc[c, "f0med"] - z.loc[c, "rate"] - z.loc[c, "db_mean"] + 0.5 * z.loc[c, "pause"],
          "wry": z.loc[c, "f0sd"] + 0.5 * z.loc[c, "pause"] - 0.5 * z.loc[c, "db_mean"],
          "tense": z.loc[c, "rate"] + z.loc[c, "db_sd"] + z.loc[c, "db_mean"] - z.loc[c, "pause"],
          "warm": z.loc[c, "f0med"] - 0.5 * z.loc[c, "rate"] - z.loc[c, "db_sd"].abs() - z.loc[c, "db_mean"].abs()}
    for k, s in sc.items():
        s = s.drop(list(used & set(s.index)))
        if len(s): i = s.idxmax(); used.add(i); refs.append((k, i))
    pools = {k: list(rng.permutation([i for i in df.index[df.cluster == k] if i not in used])) for k in df.cluster.unique()}
    held = []
    while len(held) < 15 and any(pools.values()):
        for k in pools:
            if pools[k] and len(held) < 15: held.append(pools[k].pop())
    train, tot = [], 0.0
    while tot < TRAIN_MIN * 60 and any(pools.values()):
        for k in pools:
            if pools[k] and tot < TRAIN_MIN * 60: i = pools[k].pop(); train.append(i); tot += df.dur[i]
    for split, items in (("refs", refs), ("heldout", held), ("train", train)):
        os.makedirs(f"{od}/{split}", exist_ok=True); out = []
        for it in items:
            lab, i = it if isinstance(it, tuple) else (None, it)
            r = df.loc[i]; n = os.path.basename(r.path)
            shutil.copy(r.path, f"{od}/{split}/{n}")
            out.append(dict(path=f"{split}/{n}", text=r.text, duration=round(r.dur, 2), cluster=r.cluster, **({"label": lab} if lab else {})))
        pd.DataFrame(out).to_csv(f"{od}/{split}/metadata.tsv", sep="\t", index=False, quoting=3)
    st = dict(actor=name, slug=slug, uuid=u, eligible=extracted, extracted=len(rows), kept=len(df),
              hours=round(df.dur.sum() / 3600, 2), drop=round(1 - len(good) / max(len(rows), 1), 3),
              refs=len(refs), heldout=len(held), train=len(train), train_min=round(tot / 60, 1))
    json.dump(st, open(f"{od}/stats.json", "w"))
    shutil.rmtree(f"{WORK}/{slug}/wav", ignore_errors=True)  # keep wer.tsv cache
    print(st, flush=True)

def reports(names):
    sts = [json.load(open(f)) for f in sorted(glob.glob(f"{D}/*/stats.json"))]
    s = ["# Actor datasets", "", "| actor | slug | eligible lines | extracted | kept | hours kept | WER drop rate | train min | heldout | refs |", "|---|---|---|---|---|---|---|---|---|---|"]
    for t in sts: s.append(f"| {t['actor']} | {t['slug']} | {t['eligible']} | {t['extracted']} | {t['kept']} | {t['hours']} | {t['drop']:.1%} | {t['train_min']} | {t['heldout']} | {t['refs']} |")
    open(f"{D}/SUMMARY.md", "w").write("\n".join(s) + "\n")
    h = ["<meta charset=utf-8><body style='font:15px sans-serif;max-width:900px;margin:2em auto'><h1>Reference clips per actor</h1>"]
    for t in sts:
        h.append(f"<h2>{html.escape(t['actor'])} <code>{t['slug']}</code></h2>")
        for l in list(open(f"{D}/{t['slug']}/refs/metadata.tsv"))[1:]:
            p = l.rstrip("\n").split("\t")
            h.append(f"<p><b>{p[4] if len(p) > 4 else ''}</b> ({p[2]} s): {html.escape(p[1])}<br><audio controls preload=none src='{t['slug']}/{p[0].replace('metadata.tsv', '')}'></audio></p>")
    open(f"{D}/refs.html", "w").write("\n".join(h))

if __name__ == "__main__":
    names = json.load(open(NAMES)); os.makedirs(D, exist_ok=True)
    args = sys.argv[1:]
    todo = [(u, n, slug_of(n)) for u, n in names.items() if not args or u in args or slug_of(n) in args]
    for u, n, s in todo:
        if os.path.exists(f"{D}/{s}/stats.json") and not args: continue
        build(u, n, s)
    reports(names)
