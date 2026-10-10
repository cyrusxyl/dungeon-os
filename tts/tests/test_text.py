import json
from pathlib import Path

import _path  # noqa: F401
from service.text import normalize, split_sentences

for case in json.loads((Path(__file__).parent / "fixtures/sentences.json").read_text()):
    got = split_sentences(case["in"])
    assert got == case["sentences"], (case["in"], got)

assert normalize("*bold* and _it_") == "bold and it"
assert normalize("Make a DC 14 save") == "Make a difficulty class 14 save"
assert normalize("Roll a d20 or 2d6") == "Roll a dee 20 or 2 dee 6"
assert normalize("You lose 5 HP") == "You lose 5 hit points"
assert normalize("Add +3 now") == "Add plus 3 now"
assert normalize("Wait -- no") == "Wait — no"
print("test_text ok")
