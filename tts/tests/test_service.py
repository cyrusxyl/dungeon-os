import http.client
import json
import socket
import tempfile
import threading
import time

import _path  # noqa: F401
import uvicorn
from service.app import create_app
from service.engines.mock import MockEngine
from service.queue import LIVE, WARM, Job

engine = MockEngine(chunk_delay=0.05, voices=("narrator", "astarion"))
tmp = tempfile.TemporaryDirectory()
app = create_app(engine, tmp.name)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.02)


def post(path, body):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
    return c, c.getresponse()


c = http.client.HTTPConnection("127.0.0.1", port)
c.request("GET", "/health")
h = json.loads(c.getresponse().read())
assert h["ok"] and h["engine"] == "mock" and h["sample_rate"] == 22050 and "narrator" in h["voices"], h

# /test page
c.request("GET", "/test")
tr = c.getresponse()
tb = tr.read()
assert tr.status == 200 and tr.getheader("content-type").startswith("text/html") and b"<html" in tb

# /voices, unknown voice -> 404, style fallback
c.request("GET", "/voices")
v = json.loads(c.getresponse().read())["voices"]
assert set(v) == {"narrator", "astarion"} and "wry" in v["astarion"], v
assert sorted(h["voices"]) == ["astarion", "narrator"], h
c404, r404 = post("/speak", {"text": "Hi there.", "voice": "nobody"})
assert r404.status == 404 and "nobody" in json.loads(r404.read())["error"]
n0 = len(engine.calls)
for st in (None, "neutral", "bogus"):  # all resolve to neutral: one synth, then cache hits
    cs, rs = post("/speak", {"text": "Style test line.", "voice": "astarion", "style": st})
    assert rs.status == 200 and len(rs.read()) > 0
assert len(engine.calls) == n0 + 1, engine.calls
cs, rs = post("/speak", {"text": "Style test line.", "voice": "astarion", "style": "wry"})
rs.read()
assert len(engine.calls) == n0 + 2

# chunked bytes + cache hit
body = {"text": "The door opens. *A cold* wind blows.", "voice": "narrator", "style": None, "id": "a"}
c1, r1 = post("/speak", body)
assert r1.getheader("Transfer-Encoding") == "chunked", r1.getheaders()
assert r1.getheader("X-Cache") == "miss" and r1.getheader("X-Sample-Rate") == "22050"
assert r1.getheader("Content-Type") == "application/octet-stream"
first = r1.read(1000)
assert len(first) > 0
data1 = first + r1.read()
c1.close()
assert len(data1) > 4000 and len(data1) % 2 == 0
c2, r2 = post("/speak", body)
assert r2.getheader("X-Cache") == "hit"
assert r2.read() == data1
c2.close()

# warm fills the cache, returns 202
c3, r3 = post("/warm", {"items": [{"text": "Warm line here.", "voice": "narrator"}]})
assert r3.status == 202
c3.close()
for _ in range(100):
    if len(list(app.state.cache.root.glob("*.pcm"))) >= 3:
        break
    time.sleep(0.05)
else:
    raise AssertionError("warm did not fill cache")

# priority: live before warm; new live cancels older warm
sched, order, gate = app.state.scheduler, [], threading.Event()
sched.submit(Job(LIVE, lambda j: gate.wait(5), "blocker"))
time.sleep(0.1)
w_old = sched.submit(Job(WARM, lambda j: order.append("w_old"), "w_old"))
live = sched.submit(Job(LIVE, lambda j: order.append("live"), "live"))
w_new = sched.submit(Job(WARM, lambda j: order.append("w_new"), "w_new"))
assert w_old.cancel.is_set() and not w_new.cancel.is_set()
gate.set()
for _ in range(100):
    if len(order) >= 2:
        break
    time.sleep(0.05)
assert order == ["live", "w_new"], order

# disconnect sets cancel flag; partial audio is not cached
before = len(list(app.state.cache.root.glob("*.pcm")))
c4, r4 = post("/speak", {"text": "x" * 150, "voice": "narrator", "id": "b"})
assert len(r4.read(100)) > 0
job = app.state.last_live
assert not job.cancel.is_set()
c4.sock.shutdown(socket.SHUT_RDWR)
c4.close()
for _ in range(100):
    if job.cancel.is_set():
        break
    time.sleep(0.05)
assert job.cancel.is_set(), "cancel flag not set after disconnect"
time.sleep(0.4)
assert len(list(app.state.cache.root.glob("*.pcm"))) == before

server.should_exit = True
print("test_service ok")
