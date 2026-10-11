"""Install the emotion picks as voice emotions.
Run: ~/bg3voice/venv_emo/bin/python 13_emotion_apply.py [--dry-run]
Reads ~/bg3voice/emotion/picks.json (actor -> emotion -> 3 ranked candidates) and qa.json (from 13_emotion_qa.py).
Per actor and emotion: take the candidate the QA page shows (qa idx, default 0). If it is marked bad, use the next candidate
that is not marked bad (the order wraps, but the shown one is skipped). Writes ~/bg3voice/voices/<slug>/<emotion>.{wav,txt}
(24 kHz mono) for neutral, happy, angry, sad, surprised, fearful, disgusted. Replaced files go to ~/bg3voice/voices_old/<slug>/ first.
--dry-run prints the plan and writes nothing."""
import json, os, argparse
from common import H, install_ref

D = f"{H}/emotion"


def plan(picks, qa):
    out = []
    for act, emos in sorted(picks.items()):
        for emo, lst in emos.items():
            if not lst: print(f"skip {act} {emo}: no candidate"); continue
            q = qa.get(f"{act}/{emo}", {}); i = q.get("idx", 0) % len(lst)
            if q.get("good") is False:
                if len(lst) == 1: print(f"skip {act} {emo}: bad and no alternative"); continue
                i = (i + 1) % len(lst)
            out.append((act, emo, lst[i], " (next after bad)" if q.get("good") is False else ""))
    return out



if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    picks = json.load(open(f"{D}/picks.json")); qa = json.load(open(f"{D}/qa.json")) if os.path.exists(f"{D}/qa.json") else {}
    p = plan(picks, qa)
    for act, emo, c, tag in p:
        print(f"{act:12s} {emo:8s} {c['id']} {c['dur']:.1f}s  {c['text'][:70]}{tag}")
        if not a.dry_run: install_ref(act, emo, c["path"], c["text"])
    print(len(p), "picks", "(dry run, nothing written)" if a.dry_run else "installed")
