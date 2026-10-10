"""Install one picker clip as a voice mood. Run: python3 10_apply_picks.py <slug> <mood> <clip id>
Writes ~/bg3voice/voices/<slug>/<mood>.{wav,txt} (24 kHz mono). Replaced files go to ~/bg3voice/voices_old/<slug>/ first.
Clip ids come from ~/bg3voice/picker/<slug>/pool.json."""
import os, sys, json, shutil, subprocess
from common import H
slug, mood, cid = sys.argv[1:4]
clip = next((r for r in json.load(open(f"{H}/picker/{slug}/pool.json")) if r["id"] == cid), None)
if clip is None: sys.exit(f"unknown clip id: {cid}")
vo, old = f"{H}/voices/{slug}", f"{H}/voices_old/{slug}"
os.makedirs(vo, exist_ok=True); os.makedirs(old, exist_ok=True)
for ext in ("wav", "txt"):
    f = f"{vo}/{mood}.{ext}"
    if os.path.exists(f): shutil.copy2(f, f"{old}/{mood}.{ext}")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip["path"], "-ar", "24000", "-ac", "1", f"{vo}/{mood}.wav"], check=True)
open(f"{vo}/{mood}.txt", "w").write(clip["text"].strip())
print(mood, "<-", cid)
