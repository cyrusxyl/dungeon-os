"""Score every dialogue clip with pretrained emotion models, then pick DM-emotion references per actor.
Run: ~/bg3voice/venv_emo/bin/python 13_emotion_scores.py [--rescore] [--limit N]
Models (all local, GPU):
  audio class : emotion2vec/emotion2vec_plus_large via funasr (hub=hf). Licence "other" (FunASR model licence, see model card).
  audio dim   : audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim (arousal, dominance, valence). CC-BY-NC-SA-4.0, non-commercial.
  text class  : j-hartmann/emotion-english-distilroberta-base (anger disgust fear joy neutral sadness surprise).
Pool: ~/bg3voice/emotion/pool.json (id, actor, path, text, dur: the actors' 3-10 s clips from actors/data/<slug>/{train,refs,heldout}). Raw scores are cached in ~/bg3voice/emotion/scores.parquet (reused unless --rescore).
Output: ~/bg3voice/emotion/{scores.parquet,picks.json,report.txt}.

Combine (emotions = model labels: neutral happy angry sad surprised fearful disgusted):
  A_e = audio prob, T_e = text prob, with
    neutral=neutral, happy=happy/joy, angry=angry/anger, sad=sad/sadness,
    surprised=surprised/surprise, fearful=fearful/fear, disgusted=disgusted/disgust.
  base_e = 0.6*A_e + 0.4*T_e.
  Gates use arousal, valence and dominance as percentile ranks inside the actor (0..1), so each voice is judged against itself:
    angry g=arousal*(1-valence); sad g=1-arousal; happy g=valence; surprised g=arousal;
    fearful g=arousal*(1-valence)*(1-dominance); disgusted g=1-valence; neutral g=0.
  score_e = base_e + 0.1*g   (gate is only a tie-breaker).
  Agree(e): audio top class maps to e, OR (text top class maps to e AND the hard gate passes).
    Hard gates: angry arousal>=.7 and valence<=.3; sad arousal<=.3; happy valence>=.7;
    surprised arousal>=.8; fearful arousal>=.6 and valence<=.4; disgusted valence<=.3.
Pick per actor and emotion (3 ranked candidates, a clip is the top pick for one emotion only):
  tier 1: 5-10 s, >=4 words, Agree. Tier 2 adds 3-5 s clips that Agree. Tier 3 adds 5-10 s clips that do not Agree.
  Rank = tier, then score_e + 0.05 if audio top and text top both map to e; score of a clip with fan-only names x0.85
  (so a plain clip within 15 percent of it wins)."""
import os, sys, json, re, argparse
import numpy as np, pandas as pd
import soundfile as sf
from common import H, resample

D = f"{H}/emotion"
EMO = ["neutral", "happy", "angry", "sad", "surprised", "fearful", "disgusted"]
A_MAP = {"neutral": ["neutral"], "happy": ["happy"], "angry": ["angry"], "sad": ["sad"], "surprised": ["surprised"], "fearful": ["fearful"], "disgusted": ["disgusted"]}
T_MAP = {"neutral": ["neutral"], "happy": ["joy"], "angry": ["anger"], "sad": ["sadness"], "surprised": ["surprise"], "fearful": ["fear"], "disgusted": ["disgust"]}
A_LAB = ["angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unk"]
T_LAB = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]
FAN = re.compile(r"\b(tav|baldur|faer[uû]n|absolute|sel[uû]ne|shar|lae'?zel|astarion|karlach|gale|wyll|halsin|minthara|jaheira|minsc|boo|shadowheart|orin|gortash|"
                 r"ketheric|cazador|grymforge|moonrise|githyanki|tadpole|illithid|mind flayer|emperor|cr[eè]che|nautiloid|withers|raphael|mizora|volo|zhentarim|"
                 r"harpers?|emerald grove|druid|underdark|sharess|bhaal|vlaakith|dolly|dolor|kagha|thorm|zevlor|nere|lorroakan|ulder|rolan|aradin|mol|rath|"
                 r"crown of karsus|netherstones|sceleritas|enver|myrkul|bane|cyric|jergal|shovel|cambion|tiefling|drow|dwarf|halfling|gith)\b", re.I)


def audio16(p):
    x, sr = sf.read(p, dtype="float32")
    if x.ndim > 1: x = x.mean(1)
    return resample(x, sr, 16000).astype("float32") if sr != 16000 else x


def score_all(pool, limit=None):
    import torch, torch.nn as nn
    from transformers import (Wav2Vec2Processor, Wav2Vec2Model, Wav2Vec2PreTrainedModel,
                              AutoTokenizer, AutoModelForSequenceClassification)
    from funasr import AutoModel
    pool = pool[:limit] if limit else pool
    rows = [{"id": r["id"], "actor": r["actor"], "path": r["path"], "text": r["text"], "dur": r["dur"]} for r in pool]
    # text
    tn = "j-hartmann/emotion-english-distilroberta-base"
    tk = AutoTokenizer.from_pretrained(tn); tm = AutoModelForSequenceClassification.from_pretrained(tn).cuda().eval()
    lab = [tm.config.id2label[i] for i in range(len(tm.config.id2label))]
    for i in range(0, len(rows), 64):
        b = rows[i:i + 64]
        enc = tk([r["text"] for r in b], return_tensors="pt", padding=True, truncation=True, max_length=128).to("cuda")
        with torch.no_grad(): pr = tm(**enc).logits.softmax(-1).cpu().numpy()
        for r, p in zip(b, pr):
            for l, v in zip(lab, p): r["t_" + l] = float(v)
    del tm; torch.cuda.empty_cache()
    # dimensional
    class Head(nn.Module):
        def __init__(s, c): super().__init__(); s.dense = nn.Linear(c.hidden_size, c.hidden_size); s.dropout = nn.Dropout(c.final_dropout); s.out_proj = nn.Linear(c.hidden_size, c.num_labels)
        def forward(s, x): return s.out_proj(torch.tanh(s.dense(s.dropout(x))))
    class EM(Wav2Vec2PreTrainedModel):
        def __init__(s, c): super().__init__(c); s.wav2vec2 = Wav2Vec2Model(c); s.classifier = Head(c); s.post_init()
        def forward(s, x): return s.classifier(s.wav2vec2(x)[0].mean(1))
    dn = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
    pr_ = Wav2Vec2Processor.from_pretrained(dn); dm = EM.from_pretrained(dn).cuda().eval()
    e2v = AutoModel(model="iic/emotion2vec_plus_large", hub="hf", disable_update=True)
    for k, r in enumerate(rows):
        x = audio16(r["path"])
        with torch.no_grad():
            y = pr_(x, sampling_rate=16000, return_tensors="pt").input_values.cuda()
            a, d, v = dm(y)[0].float().cpu().numpy()
        r.update(arousal=float(a), dominance=float(d), valence=float(v))
        o = e2v.generate(x, granularity="utterance", extract_embedding=False, disable_pbar=True)[0]
        for l, s in zip(o["labels"], o["scores"]): r["a_" + l.split("/")[-1].strip("<>")] = float(s)
        if k % 500 == 0: print("scored", k, len(rows), flush=True)
    return pd.DataFrame(rows)


def combine(df):
    a = df[["a_" + l for l in A_LAB]].values; t = df[["t_" + l for l in T_LAB]].values
    df["a_top"] = [A_LAB[i] for i in a.argmax(1)]; df["t_top"] = [T_LAB[i] for i in t.argmax(1)]
    df["ar"] = df.groupby("actor")["arousal"].rank(pct=True); df["va"] = df.groupby("actor")["valence"].rank(pct=True)
    df["dp"] = df.groupby("actor")["dominance"].rank(pct=True)
    gate = {"neutral": 0 * df.ar, "happy": df.va, "angry": df.ar * (1 - df.va), "sad": 1 - df.ar, "surprised": df.ar, "fearful": df.ar * (1 - df.va) * (1 - df.dp), "disgusted": 1 - df.va}
    hard = {"neutral": df.ar >= 0, "happy": df.va >= .7, "angry": (df.ar >= .7) & (df.va <= .3), "sad": df.ar <= .3, "surprised": df.ar >= .8, "fearful": (df.ar >= .6) & (df.va <= .4), "disgusted": df.va <= .3}
    for e in EMO:
        A = df[["a_" + l for l in A_MAP[e]]].sum(1); T = df[["t_" + l for l in T_MAP[e]]].sum(1)
        df["s_" + e] = 0.6 * A + 0.4 * T + 0.1 * gate[e]
        at = df.a_top.isin(A_MAP[e]); tt = df.t_top.isin(T_MAP[e])
        df["ok_" + e] = at | (tt & hard[e]); df["both_" + e] = at & tt
    df["words"] = df.text.str.split().str.len(); df["fan"] = df.text.map(lambda s: bool(FAN.search(s)))
    return df


def pick(df):
    out = {}
    for act, g in df.groupby("actor"):
        used = set(); out[act] = {}
        for e in sorted(EMO, key=lambda e: g["ok_" + e].sum()):   # scarcest emotion first
            c = g[~g.id.isin(used) & (g.words >= 4)].copy()
            c["eff"] = (c["s_" + e] + 0.05 * c["both_" + e]) * np.where(c.fan, 0.85, 1.0)
            tier = np.where(c["ok_" + e] & c.dur.between(5, 10), 1, np.where(c["ok_" + e] & c.dur.between(3, 5, inclusive="left"), 2, np.where(c.dur.between(5, 10), 3, 9)))
            c["tier"] = tier; c = c[c.tier < 9].sort_values(["tier", "eff"], ascending=[True, False])
            top = c.head(3)
            used.add(top.id.iloc[0]) if len(top) else None
            out[act][e] = [dict(id=r.id, score=round(float(r["s_" + e]), 4), tier=int(r.tier), dur=round(float(r.dur), 2), a_top=r.a_top, t_top=r.t_top,
                                agree=bool(r["both_" + e]), fan=bool(r.fan), arousal=round(float(r.ar), 2), valence=round(float(r.va), 2),
                                text=r.text, path=r.path) for _, r in top.iterrows()]
    return out


def report(df, picks):
    L = []
    L.append(f"clips {len(df)}; audio top == text top (after mapping to e2v names): ")
    m = {"anger": "angry", "disgust": "disgusted", "fear": "fearful", "joy": "happy", "neutral": "neutral", "sadness": "sad", "surprise": "surprised"}
    tt = df.t_top.map(m); L[0] += f"{(df.a_top == tt).mean():.3f}"
    L.append("\nconfusion (rows audio, cols text):\n" + pd.crosstab(df.a_top, tt).to_string())
    L.append("\nclips per speaker by audio top class:\n" + pd.crosstab(df.actor, df.a_top).to_string())
    L.append("\nclips per speaker by text top class:\n" + pd.crosstab(df.actor, df.t_top).to_string())
    L.append("\nAgree-eligible clips (ok_e, 5-10 s, >=4 words) per speaker:")
    el = pd.DataFrame({e: df[df.dur.between(5, 10) & (df.words >= 4) & df["ok_" + e]].groupby("actor").size() for e in EMO}).reindex(sorted(df.actor.unique())).fillna(0).astype(int)
    L.append(el.to_string())
    L.append("\nSpeakers with fewer than 8 eligible clips for any emotion:")
    for a, row in el.iterrows():
        th = {e: int(n) for e, n in row.items() if n < 8}
        if th: L.append(f"  {a}: {th}")
    L.append("\nAgreement per emotion (ok_e over all clips; both = audio top and text top both map to e; ok clips / audio-top clips):")
    for e in EMO: L.append(f"  {e:10s} ok {int(df['ok_' + e].sum()):5d}  both {int(df['both_' + e].sum()):5d}  audio-top {int(df.a_top.isin(A_MAP[e]).sum()):5d}  text-top {int(df.t_top.isin(T_MAP[e]).sum()):5d}")
    L.append("\npicks with tier > 1 or fewer than 3 candidates:")
    for a, d in picks.items():
        for e, c in d.items():
            if not c or c[0]["tier"] > 1 or len(c) < 3: L.append(f"  {a} {e}: n={len(c)} tiers={[x['tier'] for x in c]}")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--rescore", action="store_true"); ap.add_argument("--limit", type=int)
    a = ap.parse_args(); os.makedirs(D, exist_ok=True); f = f"{D}/scores.parquet"
    if a.rescore or not os.path.exists(f):
        df = score_all(json.load(open(f"{D}/pool.json")), a.limit)
        if not a.limit: df.to_parquet(f)
    else: df = pd.read_parquet(f)
    df = combine(df); picks = pick(df)
    json.dump(picks, open(f"{D}/picks.json", "w"), indent=1)
    r = report(df, picks); open(f"{D}/report.txt", "w").write(r); print(r)
