"""Pick several reference clips per narrator mood. The service chooses one per line, so a mood varies a little.
Run: ~/bg3voice/venv_emo/bin/python 14_mood_variants.py gen [mood ...]   make 5 near clips + 1 test line each (service must run, port 8770)
     ~/bg3voice/venv_emo/bin/python 14_mood_variants.py serve [--port 8797]   tick boxes page, saves to variants.json
     ~/bg3voice/venv_emo/bin/python 14_mood_variants.py apply   install ticked clips: <mood>.wav, <mood>.2.wav, ...
Candidates = clips of the same cluster as the kept clips, nearest to their mean in standardized f0sd, db_sd, rate, pause.
Run gen again after Save: a mood with fewer than 5 ticked keeps them and gets 5 new clips (never one shown before).
Output ~/bg3voice/picker/narrator/var/. Server is loopback only."""
import os, json, shutil, argparse, urllib.request, wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from common import H, to_24k, install_ref

D = f"{H}/picker/narrator"
V = f"{H}/voices/narrator"
CF = ["f0sd", "db_sd", "rate", "pause"]
LINES = {
    "ominous": "The candle gutters... and in the dark, something breathes. You hold very still.",
    "warm": "You pull the blanket over her shoulders, and for a moment the whole world is quiet.",
    "wry": "The innkeeper smiles warmly, which is exactly what a man with a knife behind the counter would do.",
    "tense": "A floorboard creaks upstairs. Nobody else is home.",
    "intense": "The drum thunders once, and the whole hall falls silent.",
    "urgent": "Move! The ceiling is coming down, and the door is already closing!",
    "action": "You duck under the swing, slam your shoulder into his ribs, and he crashes into the barrels.",
    "bright": "Sunlight spills across the market, and every stall smells of warm bread and honey.",
    "somber": "They buried him at dawn, and no one spoke his name.",
}
N = 5


def speak(text, voice):
    req = urllib.request.Request("http://127.0.0.1:8770/speak", json.dumps({"text": text, "voice": voice, "style": "neutral"}).encode(),
                                 {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300).read()


def installed(mood, pool):
    """Pool clips whose text equals a ref text of the mood (<mood>.txt, <mood>.2.txt ...)."""
    names = sorted(f for f in os.listdir(V) if f.split(".")[0] == mood and f.endswith(".txt"))
    texts = {open(f"{V}/{f}").read().strip() for f in names}
    return [r["id"] for r in pool if r["text"].strip() in texts]


def gen(moods):
    pool = json.load(open(f"{D}/pool.json"))
    by = {r["id"]: r for r in pool}
    X = np.array([[r[c] for c in CF] for r in pool]); X = (X - X.mean(0)) / X.std(0)
    ids = [r["id"] for r in pool]
    os.makedirs(f"{D}/var", exist_ok=True)
    meta = json.load(open(f"{D}/var/meta.json")) if os.path.exists(f"{D}/var/meta.json") else {}
    sel = json.load(open(f"{D}/variants.json")) if os.path.exists(f"{D}/variants.json") else {}
    for mood in moods or LINES:
        have = installed(mood, pool)
        if not have: print("skip", mood, "(installed clip is not in the pool)"); continue
        keep = sel.get(mood) or have
        if mood in meta and len(keep) >= N: print("skip", mood, f"({len(keep)} ticked)"); continue
        seen = set(meta.get(mood, {}).get("seen", [])) | set(meta.get(mood, {}).get("clips", [])) | set(have) | set(keep)
        c = X[[ids.index(i) for i in keep]].mean(0)
        cl = by[keep[0]]["cl"]
        near = [ids[i] for i in np.argsort(np.linalg.norm(X - c, axis=1)) if pool[i]["cl"] == cl and ids[i] not in seen][:N]
        meta[mood] = dict(line=LINES[mood], installed=have, clips=keep + near, seen=sorted(seen | set(near)))
        for cid in keep + near:
            out = f"{D}/var/{cid}_{mood}.wav"
            if os.path.exists(out): continue
            v = f"zcand-{cid}"; vd = f"{V}/../{v}"
            os.makedirs(vd, exist_ok=True)
            try:
                to_24k(by[cid]["path"], f"{vd}/neutral.wav")
                open(f"{vd}/neutral.txt", "w").write(by[cid]["text"].strip())
                pcm = speak(LINES[mood], v)
            finally:
                shutil.rmtree(vd)
            with wave.open(out, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            shutil.copy(by[cid]["path"], f"{D}/var/{cid}_ref.wav")
            print(mood, cid, flush=True)
        json.dump(meta, open(f"{D}/var/meta.json", "w"), indent=1)
    page(meta, by)


def page(meta, by):
    sel = json.load(open(f"{D}/variants.json")) if os.path.exists(f"{D}/variants.json") else {}
    h = ["<!doctype html><meta charset=utf-8><title>Mood variants</title><style>body{font:15px system-ui;margin:20px}td,th{padding:6px 10px;border-bottom:1px solid #ccc;vertical-align:top;text-align:left}h2{margin-top:28px}</style>",
         "<h1>Narrator mood variants</h1><p>Tick every clip that fits the mood. The service picks one per line. Tick at least one per mood.</p><button onclick=save()>Save</button> <span id=s></span>"]
    for mood, m in meta.items():
        h.append(f"<h2>{mood}</h2><p><i>{m['line']}</i></p><table><tr><th></th><th>clip</th><th>reference text</th><th>original</th><th>test line</th></tr>")
        on = sel.get(mood, m["installed"])
        for cid in m["clips"]:
            r = by[cid]
            h.append(f"<tr><td><input type=checkbox data-m='{mood}' value='{cid}' {'checked' if cid in on else ''}></td><td>{cid}<br>rate {r['rate']:.1f}{'<br><b>installed</b>' if cid in m['installed'] else ''}</td>"
                     f"<td>{r['text']}</td><td><audio controls preload=none src='var/{cid}_ref.wav'></audio></td><td><audio controls preload=none src='var/{cid}_{mood}.wav'></audio></td></tr>")
        h.append("</table>")
    h.append("<script>function save(){const o={};document.querySelectorAll('input[type=checkbox]').forEach(c=>{(o[c.dataset.m]??=[]);if(c.checked)o[c.dataset.m].push(c.value)});"
             "fetch('/save',{method:'POST',body:JSON.stringify(o)}).then(r=>s.textContent=r.ok?'saved':'error')}</script>")
    open(f"{D}/variants.html", "w").write("".join(h))


def serve(port):
    class Hd(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=D, **k)
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            json.dump(json.loads(body), open(f"{D}/variants.json", "w"), indent=1)
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass
    print(f"http://127.0.0.1:{port}/variants.html")
    ThreadingHTTPServer(("127.0.0.1", port), Hd).serve_forever()


def apply():
    pool = {r["id"]: r for r in json.load(open(f"{D}/pool.json"))}
    sel = json.load(open(f"{D}/variants.json"))
    old = f"{H}/voices_old/narrator"; os.makedirs(old, exist_ok=True)
    for mood, cids in sel.items():
        if not cids: print("skip", mood, "(nothing ticked)"); continue
        for f in os.listdir(V):
            if f.split(".")[0] == mood and f[-4:] in (".wav", ".txt"):
                shutil.move(f"{V}/{f}", f"{old}/{f}")
        for i, cid in enumerate(cids):
            install_ref("narrator", mood if i == 0 else f"{mood}.{i + 1}", pool[cid]["path"], pool[cid]["text"])
        print(mood, "<-", ", ".join(cids))


ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["gen", "serve", "apply"]); ap.add_argument("moods", nargs="*"); ap.add_argument("--port", type=int, default=8797)
a = ap.parse_args()
if a.cmd == "gen": gen(a.moods)
elif a.cmd == "serve": serve(a.port)
else: apply()
