"""Map narrator wav clips to cleaned loca text; keep 1.5-15 s. Out: ~/bg3voice/candidates.tsv"""
import re, glob, os, soundfile as sf
from common import H, loca, clean
stats = dict(total=0, notext=0, var=0, dur=0, kept=0)
out = open(f"{H}/candidates.tsv", "w")
for p in sorted(glob.glob(f"{H}/wav/vNARRATOR_h*.wav")):
    stats["total"] += 1
    h = os.path.basename(p)[len("vNARRATOR_"):-4]
    raw = loca().get(h)
    if raw is None or not raw.strip(): stats["notext"] += 1; continue
    if re.search(r"\[\d+\]", raw): stats["var"] += 1; continue
    t = clean(raw)
    if not t: stats["notext"] += 1; continue
    d = sf.info(p).duration
    if not 1.5 <= d <= 15: stats["dur"] += 1; continue
    stats["kept"] += 1
    out.write(f"{p}\t{t}\t{d:.2f}\n")
print(stats)
