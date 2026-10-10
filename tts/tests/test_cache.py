import tempfile

import _path  # noqa: F401
from service.cache import Cache, make_key

k = make_key("mock", "1", "narrator", None, "Hello.")
assert len(k) == 64 and k == make_key("mock", "1", "narrator", None, "Hello.")
assert k != make_key("mock", "2", "narrator", None, "Hello.")
assert k != make_key("mock", "1", "narrator", "grim", "Hello.")
assert k != make_key("mock", "1", "other", None, "Hello.")
with tempfile.TemporaryDirectory() as d:
    c = Cache(d)
    assert not c.has(k) and c.get(k) is None
    c.put(k, b"\x01\x02", {"text": "Hello."})
    assert c.has(k) and c.get(k) == b"\x01\x02"
    assert (c.root / f"{k}.json").exists()
print("test_cache ok")
