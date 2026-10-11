"""QA page for the emotion picks. Run: ~/bg3voice/venv_emo/bin/python 13_emotion_qa.py  (http://127.0.0.1:8796/)
Shows the top pick per actor for each emotion, with an 'alternative' button (cycles the 3 candidates), a good/bad toggle and a note.
Reads ~/bg3voice/emotion/picks.json. Saves each change to ~/bg3voice/emotion/qa.json: {"actor/emotion": {"idx": 0, "good": true|false|null, "note": ""}}.
Audio is the original clip, served only for ids in picks.json."""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from common import H

D = f"{H}/emotion"; PORT = 8796
PAGE = r"""<!doctype html><meta charset=utf-8><title>Emotion picks QA</title>
<style>body{font:14px sans-serif;margin:12px;background:#fafafa}h2{margin:18px 0 6px;position:sticky;top:0;background:#fafafa}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}.c{border:1px solid #bbb;border-radius:6px;padding:6px;background:#fff}
.c.good{border-color:#2a2;background:#efe}.c.bad{border-color:#c22;background:#fee}.t{font-size:12px;color:#333;margin:4px 0}.m{font-size:11px;color:#666}
audio{width:100%;height:30px}button{margin-right:4px}input{width:95%}</style><body><div id=app>loading</div><script>
let P,Q;const E=["neutral","happy","angry","sad","surprised","fearful","disgusted"];
const save=()=>fetch('/api/qa',{method:'POST',body:JSON.stringify(Q)});
const st=(a,e)=>Q[a+'/'+e]||(Q[a+'/'+e]={idx:0,good:null,note:''});
function draw(){let h='';for(const e of E){h+=`<h2>${e}</h2><div class=g>`;for(const a of Object.keys(P).sort()){const l=P[a][e],s=st(a,e);
if(!l.length){h+=`<div class=c>${a}: no clip</div>`;continue}const c=l[s.idx%l.length];
h+=`<div class="c ${s.good===true?'good':s.good===false?'bad':''}"><b>${a}</b> <span class=m>#${s.idx%l.length+1}/${l.length} score ${c.score} tier ${c.tier} ${c.dur}s</span>
<audio controls preload=none src="/audio/${c.id}"></audio><div class=t>${c.text}</div><div class=m>audio: ${c.a_top} | text: ${c.t_top}${c.agree?' | agree':''}${c.fan?' | fan name':''}</div>
<button onclick="S('${a}','${e}','good')">good</button><button onclick="S('${a}','${e}','bad')">bad</button><button onclick="S('${a}','${e}','alt')">alternative</button>
<input value="${(s.note||'').replace(/"/g,'&quot;')}" placeholder=note onchange="N('${a}','${e}',this.value)"></div>`}h+='</div>'}
document.getElementById('app').innerHTML=h}
function S(a,e,k){const s=st(a,e);if(k=='alt')s.idx=(s.idx+1)%P[a][e].length;else s.good=s.good===(k=='good')?null:k=='good';save();draw()}
function N(a,e,v){st(a,e).note=v;save()}
Promise.all([fetch('/api/picks').then(r=>r.json()),fetch('/api/qa').then(r=>r.json())]).then(([p,q])=>{P=p;Q=q;draw()});
</script>"""


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"): return self.send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/picks": return self.send(200, open(f"{D}/picks.json").read())
        if self.path == "/api/qa": return self.send(200, open(f"{D}/qa.json").read() if os.path.exists(f"{D}/qa.json") else "{}")
        if self.path.startswith("/audio/"):
            cid = self.path[7:]
            for emos in self.server.picks.values():
                for lst in emos.values():
                    for c in lst:
                        if c["id"] == cid: return self.send(200, open(c["path"], "rb").read(), "audio/wav")
        self.send(404, "{}")

    def do_POST(self):
        if self.path != "/api/qa": return self.send(404, "{}")
        q = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        json.dump(q, open(f"{D}/qa.json", "w"), indent=1); self.send(200, "{}")


if __name__ == "__main__":
    s = ThreadingHTTPServer(("127.0.0.1", PORT), Hd); s.picks = json.load(open(f"{D}/picks.json"))
    open(f"{D}/index.html", "w").write(PAGE)
    s.serve_forever()
