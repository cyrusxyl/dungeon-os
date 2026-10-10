"""Reference-clip picker with free-text cluster notes.
Run: ~/bg3voice/bench/f5tts/.venv/bin/python 09_ref_picker.py <slug> [--port 8790] [--rebuild]
Needs plotly in that venv (uv pip install plotly).
Pool: narrator = kept.tsv + norm/24k; actor = actors/data/<slug>/{train,refs,heldout}.
Keep 6-10 s, exact text (narrator: WER 0), no brackets. No speed or expressiveness filter.
KMeans (--k, default 10) on standardized f0sd, db_sd, rate, pause. 5 clips per cluster are ground truth: nearest the centroid, then farthest-first within the closest 20 percent.
Each gets 2 stock F5TTS_v1_Base zero-shot test lines (nfe 32, seed 1).
Output ~/bg3voice/picker/<slug>/: index.html, plotly.min.js, pool.json, cluster_features.json, notes.json, wav/.
Notes save as typed (POST /save) to notes.json. Server is loopback only."""
import os, re, json, html, shutil, argparse
import numpy as np, pandas as pd, soundfile as sf
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from common import H
LINES = ["The candle gutters... and in the dark, something breathes. You hold very still.",
         "Was that a footstep, or only your own heart? Run!"]
F = ["f0med", "f0sd", "db_mean", "db_sd", "rate", "pause"]
FN = {"f0med": "median pitch", "f0sd": "pitch sd", "db_mean": "loudness", "db_sd": "loudness sd",
      "rate": "speaking rate", "pause": "pause share"}
CF = ["f0sd", "db_sd", "rate", "pause"]  # clustering features: db_mean (r=-0.6 with db_sd) and f0med (weak) are dropped


def feats(r):
    import librosa
    w, t, d = r
    a, sr = sf.read(w, dtype="float32")
    if a.ndim > 1: a = a.mean(1)
    hop = 240
    db = 20 * np.log10(librosa.feature.rms(y=a, frame_length=960, hop_length=hop)[0] + 1e-6)
    act = db > db.max() - 35
    f0 = librosa.yin(a, fmin=60, fmax=400, sr=sr, frame_length=1440, hop_length=hop)
    m = min(len(f0), len(act)); v = f0[:m][act[:m] & (f0[:m] < 395) & (f0[:m] > 65)]
    lv = np.log2(v) if len(v) > 20 else np.array([7.0, 7.0])
    return dict(path=w, text=t, dur=len(a) / sr, f0med=float(np.median(lv)), f0sd=float(lv.std()),
                db_mean=float(db[act].mean()), db_sd=float(db[act].std()), pause=float(1 - act.mean()))


def pool(slug):
    if slug == "narrator":
        d = pd.read_csv(f"{H}/kept.tsv", sep="\t", quoting=3)
        d = d[(d.dur >= 6) & (d.dur <= 10) & (d.wer == 0) & ~d.text.str.contains(r"[\[\]]")].copy()
        d["path"] = [f"{H}/norm/24k/{os.path.basename(p)}" for p in d.path]
        return d[["path", "text", "dur"] + [c for c in F if c != "rate"]].reset_index(drop=True)
    from multiprocessing import Pool
    rows = []; base = f"{H}/actors/data/{slug}"
    for sp in ("train", "refs", "heldout"):
        d = pd.read_csv(f"{base}/{sp}/metadata.tsv", sep="\t", quoting=3)
        rows += [(f"{base}/{sp}/{os.path.basename(r.path)}", r.text, r.duration) for r in d.itertuples()
                 if 6 <= r.duration <= 10 and not re.search(r"[\[\]]", r.text)]
    with Pool(6) as p: return pd.DataFrame(p.map(feats, rows, chunksize=8))


def select(slug, k):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    df = pool(slug)
    df = df[df.path.map(os.path.exists)].reset_index(drop=True)
    df["rate"] = df.text.str.len() / df.dur
    Z = StandardScaler().fit_transform(df[CF])
    km = KMeans(min(k, len(df)), n_init=10, random_state=0).fit(Z)
    df["cl"] = km.labels_
    order = df.groupby("cl").rate.mean().sort_values().index          # number clusters by speaking rate
    df["cl"] = df.cl.map({c: i + 1 for i, c in enumerate(order)})
    cen = {df.cl[km.labels_ == c].iloc[0]: km.cluster_centers_[c] for c in range(km.n_clusters)}
    pca = PCA(3).fit(Z); P = pca.transform(Z)
    df[["pc1", "pc2", "pc3"]] = P
    df["id"] = [f"p{i:04d}" for i in range(len(df))]
    df["dist"] = [np.linalg.norm(Z[i] - cen[df.cl[i]]) for i in range(len(df))]
    df["chosen"] = False
    for c, g in df.groupby("cl"):   # nearest to centroid, then farthest-first inside the closest 20 percent
        near = g.dist.nsmallest(max(5, int(len(g) * 0.2))).index.tolist()
        sel = [near[0]]
        while len(sel) < min(5, len(near)):
            sel.append(max((i for i in near if i not in sel), key=lambda i: min(np.linalg.norm(Z[i] - Z[j]) for j in sel)))
        df.loc[sel, "chosen"] = True
    load = {f"PC{i + 1}": {f: round(float(pca.components_[i][j]), 2) for j, f in enumerate(CF)} for i in range(3)}
    return df, dict(loadings=load, var=[round(float(v), 3) for v in pca.explained_variance_ratio_])


def build(slug, od, k, rebuild_audio):
    os.makedirs(f"{od}/wav", exist_ok=True)
    df, pcainfo = select(slug, k)
    todo = [r for r in df[df.chosen].itertuples() if rebuild_audio or not os.path.exists(f"{od}/wav/{r.id}_t2.wav")]
    if todo:
        from f5_tts.api import F5TTS
        m = F5TTS(model="F5TTS_v1_Base", device="cuda")
        for r in todo:
            for k, line in enumerate(LINES):
                w, sr, _ = m.infer(r.path, r.text, line, show_info=lambda *a: None, seed=1, nfe_step=32, progress=None)
                sf.write(f"{od}/wav/{r.id}_t{k + 1}.wav", np.asarray(w, dtype="float32").squeeze(), sr)
            print(r.id, flush=True)
    cf = {}; mu, sd = df[F].mean(), df[F].std()
    for c, g in df.groupby("cl"):
        z = {f: round(float((g[f].mean() - mu[f]) / sd[f]), 2) for f in F}
        cf[f"{c:02d}"] = dict(n=len(g), means={f: round(float(g[f].mean()), 3) for f in F}, z=z, label=label(z),
                              clips=[r.id for r in g[g.chosen].itertuples()])
    json.dump(dict(features=F, clusters=cf, **pcainfo), open(f"{od}/cluster_features.json", "w"), indent=1)
    df.drop(columns=["dist"]).to_json(f"{od}/pool.json", orient="records", indent=0)
    import plotly
    shutil.copy(os.path.join(os.path.dirname(plotly.__file__), "package_data", "plotly.min.js"), f"{od}/plotly.min.js")
    page(slug, od, df, cf, pcainfo)


def label(z):
    w = {"rate": ("slow", "fast"), "f0sd": ("flat pitch", "wide pitch"), "db_sd": ("even loudness", "dynamic"),
         "pause": ("few pauses", "many pauses"), "db_mean": ("quiet", "loud"), "f0med": ("low voice", "high voice")}
    t = [(abs(v), w[f][v > 0]) for f, v in z.items() if abs(v) >= 0.4]
    return ", ".join(x for _, x in sorted(t, reverse=True)[:4]) or "average"


def ztable(cf):
    def bg(v):
        a = min(abs(v) / 1.5, 1) * 0.7
        return f"rgba({'220,90,70' if v > 0 else '70,130,220'},{a:.2f})"
    h = "".join(f"<th>{FN[f]}</th>" for f in F)
    rows = "".join(f"<tr><td>{int(c)}</td><td style='text-align:left'>{html.escape(v['label'])}</td><td>{v['n']}</td>" +
                   "".join(f"<td style='background:{bg(v['z'][f])}'>{v['z'][f]:+.2f}</td>" for f in F) + "</tr>" for c, v in cf.items())
    return (f"<table id=zt><tr><th>#</th><th>label</th><th>clips</th>{h}</tr>{rows}</table>"
            "<p class=d>Cells are z-scores against the whole pool. Red is above average, blue is below.</p>")


def hulls(df):
    from scipy.spatial import ConvexHull
    out = {}
    for c, g in df.groupby("cl"):
        p = g[["pc1", "pc2"]].values
        if len(p) >= 3:
            try:
                h = p[ConvexHull(p).vertices]; out[int(c)] = np.vstack([h, h[:1]]).round(3).tolist()
            except Exception: pass
    return out


JS = r"""
const D=window.DATA;
const pal=['#e6194b','#3cb44b','#4363d8','#f58231','#911eb4','#42d4f4','#f032e6','#bfef45','#fabed4','#469990','#dcbeff','#9a6324','#fffac8','#800000','#aaffc3','#808000','#ffd8b1','#000075','#a9a9a9','#e8c547'];
const cols=c=>pal[(c-1)%pal.length];
const player=document.getElementById('player');
function play(id){player.src='/clip/'+id+'.wav';player.play();}
function goto(c){document.getElementById('cl'+c).scrollIntoView({behavior:'smooth',block:'start'});}
const cls=[...new Set(D.pool.map(p=>p.cl))].sort((a,b)=>a-b);
const hov=p=>p.id+'<br>'+p.text.slice(0,90)+'<br>'+p.dur.toFixed(1)+' s, '+p.rate.toFixed(1)+' chars/s';
const pts=(c,gt)=>D.pool.filter(p=>p.cl==c&&p.gt==gt);
const T2=[],T3=[];
for(const c of cls){
  const h=D.hulls[c]||[[0,0]];
  T2.push({type:'scatter',mode:'lines',x:h.map(a=>a[0]),y:h.map(a=>a[1]),fill:'toself',fillcolor:cols(c)+'00',line:{color:cols(c),width:1},hoverinfo:'skip',showlegend:false,meta:{c,k:'hull'}});
  const a=pts(c,false),g=pts(c,true);
  T2.push({type:'scatter',mode:'markers',x:a.map(p=>p.pc1),y:a.map(p=>p.pc2),customdata:a.map(p=>p.id),text:a.map(hov),hoverinfo:'text',marker:{size:4,color:cols(c),opacity:.55},showlegend:false,meta:{c,k:'pts'}});
  T2.push({type:'scatter',mode:'markers',x:g.map(p=>p.pc1),y:g.map(p=>p.pc2),customdata:g.map(p=>p.id),text:g.map(hov),hoverinfo:'text',marker:{size:13,color:cols(c),line:{color:'#fff',width:2.5}},showlegend:false,meta:{c,k:'gt'}});
  T3.push({type:'scatter3d',mode:'markers',x:a.map(p=>p.pc1),y:a.map(p=>p.pc2),z:a.map(p=>p.pc3),customdata:a.map(p=>p.id),text:a.map(hov),hoverinfo:'text',marker:{size:2.5,color:cols(c),opacity:.55},showlegend:false,meta:{c,k:'pts'}});
  T3.push({type:'scatter3d',mode:'markers',x:g.map(p=>p.pc1),y:g.map(p=>p.pc2),z:g.map(p=>p.pc3),customdata:g.map(p=>p.id),text:g.map(hov),hoverinfo:'text',marker:{size:7,color:cols(c),line:{color:'#fff',width:3}},showlegend:false,meta:{c,k:'gt'}});
  const m=k=>D.pool.filter(p=>p.cl==c).reduce((s,p)=>s+p[k],0)/D.pool.filter(p=>p.cl==c).length;
  T3.push({type:'scatter3d',mode:'markers+text',x:[m('pc1')],y:[m('pc2')],z:[m('pc3')],text:[String(c)],textposition:'top center',hoverinfo:'skip',marker:{size:8,symbol:'diamond',color:cols(c),line:{color:'#000',width:1}},textfont:{color:'#fff',size:13},showlegend:false,meta:{c,k:'cen'}});
}
// 2D cluster number labels
const L2=cls.map(c=>{const h=D.pool.filter(p=>p.cl==c);return{x:h.reduce((s,p)=>s+p.pc1,0)/h.length,y:h.reduce((s,p)=>s+p.pc2,0)/h.length,text:'<b>'+c+'</b>',showarrow:false,font:{color:'#fff',size:13},captureevents:true,name:'L'+c}});
const lay={paper_bgcolor:'#14151a',plot_bgcolor:'#1b1d24',font:{color:'#ccc'},margin:{l:30,r:5,t:5,b:30},height:340,dragmode:'pan'};
const ax=n=>({title:n,gridcolor:'#2a2d38',zerolinecolor:'#444'});
const PC=['PC1','PC2','PC3'].map((n,i)=>n+' ('+(D.pca.var[i]*100).toFixed(0)+'%)');
const g2=document.getElementById('g2'),g3=document.getElementById('g3');
Plotly.newPlot(g2,T2,{...lay,xaxis:ax(PC[0]),yaxis:ax(PC[1]),annotations:L2},{displayModeBar:false,scrollZoom:true});
Plotly.newPlot(g3,T3,{...lay,scene:{xaxis:ax(PC[0]),yaxis:ax(PC[1]),zaxis:ax(PC[2]),bgcolor:'#1b1d24'}},{displayModeBar:false});
function onclick(ev){const p=ev.points&&ev.points[0];if(!p||!p.customdata)return;const id=p.customdata,rec=D.pool.find(x=>x.id==id);play(id);if(rec.gt)goto(rec.cl);}
g2.on('plotly_click',onclick);g3.on('plotly_click',onclick);
g2.on('plotly_clickannotation',e=>goto(parseInt(e.annotation.name.slice(1))));
let mode='2d';
function setMode(m){mode=m;g2.style.display=m=='2d'?'block':'none';g3.style.display=m=='3d'?'block':'none';
  document.getElementById('tg').textContent=m=='2d'?'Show 3D':'Show 2D';(m=='2d'?g2:g3).dispatchEvent(new Event('resize'));Plotly.Plots.resize(m=='2d'?g2:g3);cur&&highlight(cur);}
document.getElementById('tg').onclick=()=>setMode(mode=='2d'?'3d':'2d');
g3.style.display='none';
let cur=null;
function highlight(c){cur=c;
  const T=mode=='2d'?T2:T3,g=mode=='2d'?g2:g3;
  const idx=T.map((t,i)=>i);
  Plotly.restyle(g,{opacity:T.map(t=>t.meta.c==c?1:.12)},idx);
  if(mode=='2d')Plotly.restyle(g,{fillcolor:T.map(t=>t.meta.k=='hull'?cols(t.meta.c)+(t.meta.c==c?'66':'00'):cols(t.meta.c)+'00')},idx.filter(i=>T[i].meta.k=='hull'));
  const f=D.cf[String(c).padStart(2,'0')];
  document.getElementById('ro').innerHTML='<b style="color:'+cols(c)+'">Cluster '+c+'</b> ('+f.n+' clips)<br>'+f.label+'<br>rate '+f.means.rate.toFixed(1)+' chars/s<br>pitch sd '+f.means.f0sd.toFixed(2)+' oct<br>loudness sd '+f.means.db_sd.toFixed(1)+' dB<br>pause '+(f.means.pause*100).toFixed(0)+'%';}
const io=new IntersectionObserver(es=>{for(const e of es)if(e.isIntersecting)highlight(parseInt(e.target.dataset.c));},{rootMargin:'-45% 0px -50% 0px'});
document.querySelectorAll('section[data-c]').forEach(s=>io.observe(s));
// notes
let notes={};
const timers={};
function save(c,clip,text){fetch('/save',{method:'POST',body:JSON.stringify({cluster:c,clip:clip,text:text})});}
fetch('/notes.json?'+Date.now()).then(r=>r.json()).then(n=>{notes=n;
  document.querySelectorAll('textarea[data-c],input[data-c]').forEach(e=>{const x=notes[e.dataset.c]||{};
    e.value=e.dataset.clip?((x.clips||{})[e.dataset.clip]||''):(x.note||'');
    e.addEventListener('input',()=>{clearTimeout(timers[e.dataset.c+e.dataset.clip]);
      timers[e.dataset.c+e.dataset.clip]=setTimeout(()=>{save(e.dataset.c,e.dataset.clip||null,e.value);e.style.outline='1px solid #4a4'},250);});});});
"""

CSS = """body{font:15px system-ui;background:#14151a;color:#e8e6e1;margin:0}#top{position:sticky;top:0;z-index:5;background:#14151a;border-bottom:1px solid #333;padding:6px 12px}
#wrap{display:flex;gap:10px}#maps{flex:1;min-width:0}#side{width:210px;font-size:13px}#cap{color:#9a9aa5;font-size:12px}
main{max-width:900px;margin:auto;padding:12px}section{background:#1e2028;border-radius:8px;padding:10px 14px;margin:14px 0;scroll-margin-top:470px}
.d{color:#9a9aa5;font-size:13px}audio{width:100%;margin:2px 0}.clip{border-top:1px solid #333;padding:8px 0}
#zt{border-collapse:collapse;font-size:13px;margin:8px 0}#zt td,#zt th{padding:3px 8px;text-align:center;border:1px solid #333}
textarea{width:100%;height:110px;background:#14151a;color:#e8e6e1;border:1px solid #444;border-radius:4px;font:inherit;box-sizing:border-box}
input[type=text]{width:100%;background:#14151a;color:#e8e6e1;border:1px solid #444;border-radius:4px;box-sizing:border-box;font-size:13px}button{cursor:pointer}"""


def page(slug, od, df, cf, pcainfo):
    data = dict(pool=[dict(id=r.id, cl=int(r.cl), gt=bool(r.chosen), pc1=round(r.pc1, 3), pc2=round(r.pc2, 3), pc3=round(r.pc3, 3),
                           text=r.text, dur=round(r.dur, 2), rate=round(r.rate, 2)) for r in df.itertuples()],
                hulls=hulls(df), pca=pcainfo, cf=cf)
    cap = "; ".join(f"PC{i + 1} ({pcainfo['var'][i] * 100:.0f}%): " + ", ".join(
        f"{FN[f]} {v:+.2f}" for f, v in sorted(pcainfo["loadings"][f"PC{i + 1}"].items(), key=lambda kv: -abs(kv[1]))[:3])
        for i in range(3))
    o = [f"<!doctype html><meta charset=utf-8><title>Ref picker: {slug}</title><style>{CSS}</style>",
         f"<div id=top><div id=wrap><div id=maps><div id=g2></div><div id=g3></div></div><div id=side>"
         f"<button id=tg>Show 3D</button><div id=ro style='margin:8px 0'>Scroll to a cluster.</div>"
         f"<audio id=player controls></audio></div></div><div id=cap>Pool of {len(df)} clips. Big ringed points are the ground-truth clips. "
         f"Axes (strongest loadings): {html.escape(cap)}</div></div><main><h1>Ref picker: {slug}</h1>",
         ztable(cf), "<p class=d>Test lines: " + " / ".join(html.escape(l) for l in LINES) + "</p>"]
    for c, g in df.groupby("cl"):
        m = cf[f"{c:02d}"]["means"]
        o.append(f"<section id=cl{c} data-c={c}><h2>Cluster {c}: {html.escape(cf[f"{c:02d}"]["label"])}</h2><div class=d>rate {m['rate']:.1f} chars/s, pitch sd {m['f0sd']:.2f} oct, "
                 f"loudness sd {m['db_sd']:.1f} dB, pause {m['pause'] * 100:.0f}%, {len(g)} clips in pool</div>")
        for r in g[g.chosen].itertuples():
            o.append(f"<div class=clip><b>{r.id}</b> &mdash; {r.dur:.1f} s<br>{html.escape(r.text)}"
                     f"<br>Original <audio controls preload=none src='/clip/{r.id}.wav'></audio>"
                     f"Line 1 <audio controls preload=none src='wav/{r.id}_t1.wav'></audio>"
                     f"Line 2 <audio controls preload=none src='wav/{r.id}_t2.wav'></audio>"
                     f"<input type=text data-c={c} data-clip={r.id} placeholder='optional note on this clip'></div>")
        o.append(f"<p>How do these feel? (mood, pace, what is good or bad)</p><textarea data-c={c}></textarea></section>")
    o.append(f"</main><script src=plotly.min.js></script><script>window.DATA={json.dumps(data)};{JS}</script>")
    open(f"{od}/index.html", "w").write("\n".join(o))


def serve(od, port):
    NOTES = f"{od}/notes.json"
    paths = {r["id"]: r["path"] for r in json.load(open(f"{od}/pool.json"))}

    class Hd(SimpleHTTPRequestHandler):
        def __init__(s, *a, **k): super().__init__(*a, directory=od, **k)

        def do_GET(s):
            if s.path.startswith("/clip/"):
                p = paths.get(os.path.basename(s.path).removesuffix(".wav"))
                if not p: return s.send_error(404)
                b = open(p, "rb").read()
                s.send_response(200); s.send_header("Content-Type", "audio/wav"); s.send_header("Content-Length", str(len(b)))
                s.end_headers(); s.wfile.write(b); return
            if s.path.split("?")[0] == "/notes.json" and not os.path.exists(NOTES):
                b = b"{}"; s.send_response(200); s.send_header("Content-Length", "2"); s.end_headers(); s.wfile.write(b); return
            super().do_GET()

        def do_POST(s):
            if s.path != "/save": return s.send_error(404)
            d = json.loads(s.rfile.read(int(s.headers["Content-Length"])))
            cur = json.load(open(NOTES)) if os.path.exists(NOTES) else {}
            c = cur.setdefault(str(d["cluster"]), {})
            if d.get("clip"): c.setdefault("clips", {})[d["clip"]] = d["text"]
            else: c["note"] = d["text"]
            tmp = NOTES + ".tmp"; json.dump(cur, open(tmp, "w"), indent=1, ensure_ascii=False); os.replace(tmp, NOTES)
            s.send_response(204); s.end_headers()

    ThreadingHTTPServer(("127.0.0.1", port), Hd).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slug"); ap.add_argument("--port", type=int, default=8790); ap.add_argument("--rebuild", action="store_true"); ap.add_argument("--k", type=int, default=10)
    a = ap.parse_args(); od = f"{H}/picker/{a.slug}"
    if a.rebuild or not os.path.exists(f"{od}/index.html"): build(a.slug, od, a.k, False)
    serve(od, a.port)
