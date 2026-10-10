"""F5 engine smoke test. Skipped without CUDA or the gpu extra."""
import sys
import time

import _path  # noqa: F401

try:
    import torch
    import f5_tts  # noqa: F401
    ok = torch.cuda.is_available()
except ImportError:
    ok = False
if not ok:
    print("SKIP: no CUDA or gpu extra")
    sys.exit(0)

import numpy as np
from service.engines.f5 import F5Engine

e = F5Engine()
text = "The candle gutters, and in the dark, something breathes."
t0 = time.time()
first = None
parts = []
for a in e.stream(text, "narrator", None):
    first = first or time.time() - t0
    assert a.dtype == np.int16 and a.ndim == 1
    parts.append(a)
total = time.time() - t0
secs = sum(len(a) for a in parts) / e.sample_rate
assert secs > 1.0, secs
print(f"ok first chunk {first:.2f}s, total {total:.2f}s, audio {secs:.2f}s, RTF {total / secs:.2f}")
