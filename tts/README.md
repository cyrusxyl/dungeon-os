# DungeonOS narration TTS

Separate uv project. Do not add torch to the root project.

## Run
    cd tts
    uv run uvicorn service.app:app --port 8770

The service binds to 127.0.0.1 by default. `/speak` and `/warm` have no auth.
A LAN bind (`--host 0.0.0.0`) needs a firewall rule or a token in front of it.

Set `TTS_ENGINE` to pick the engine. The default is `mock` (tones, no GPU).
Set `TTS_ENGINE=f5` for the real voice (F5-TTS on CUDA).
Set `TTS_CACHE` to move the cache. The default is `tts/cache/`.

## Test
    cd tts
    for t in tests/test_*.py; do uv run python $t; done

## API
`POST /speak`, `POST /warm`, `GET /voices`, `GET /health`, `GET /test`.
`/speak` takes `text`, `voice` (slug) and `style` (label). An unknown style uses neutral.
An unknown voice returns 404 with `{"error": ...}`. `X-Cache` says `hit` or `miss`.
`GET /voices` lists `{"voices": {slug: [labels]}}`. `GET /health` lists the slugs.

## GPU engine (F5-TTS)
Install the optional extra. It pulls torch 2.8 (cu128) and f5-tts.

    cd tts
    uv sync --extra gpu
    TTS_ENGINE=f5 .venv/bin/uvicorn service.app:app --port 8770

The model loads once at startup and stays on the GPU. Startup warms it up.
Env vars:
- `BG3_VOICE_HOME`: home of the voice data. Default `~/bg3voice`.
- `TTS_VOICES_DIR`: voice library. Default `$BG3_VOICE_HOME/voices`.

Every voice is stock `F5TTS_v1_Base` plus reference clips.

Voice library layout: `<slug>/<label>.wav` + `<slug>/<label>.txt` (exact ref text, 24 kHz mono, 6-10 s).
Labels: neutral, ominous, wry, tense, warm. Each voice needs `neutral`.
The service scans the library once. It scans again when a voice folder changes.

GPU test (skips itself without CUDA):

    .venv/bin/python tests/test_f5_engine.py

## Tools (local only)
These scripts need the BG3 install and Windows tools through WSL. Run them with `~/bg3voice/bench/f5tts/.venv/bin/python`.
`tools/common.py` holds the shared paths and helpers. Env: `BG3_VOICE_HOME`, `BG3_WIN_HOME`, `BG3_LOCA_XML`, `BG3_DIVINE_EXE`, `BG3_VOICE_PAK`.
- `01_map_text.py`: match narrator clips to loca text, keep 1.5-15 s.
- `02_whisper_filter.py`: Whisper WER of each clip against its text.
- `03_normalize_features.py`: keep WER <= 0.1, normalize loudness, compute prosody features.
- `07_actor_dataset.py`: build the per-actor dataset (refs, train, heldout). Reads `tools/actors.json` (UUID to name).
- `08_build_voice_library.py`: copy actor refs into the voice library. Skips clips that exist. `--force` overwrites.
- `09_ref_picker.py`: listening page to pick the best ref clips.
- `10_apply_picks.py`: install a picked clip as a voice mood.

## Voices for NPCs
Narration uses the `narrator` voice. A `say` line is voiced only if its actor has a voice.
Write the map in `<campaign>/stage/voices.json`. See `stage/voices.example.json`.

    {"innkeeper": "minsc", "villain": "emperor"}

Keys are actor ids. Values are voice slugs. A slug is a folder name in the voice library:
narrator, astarion, shadowheart, laezel, gale, karlach, wyll, halsin, minthara, jaheira, minsc, emperor, tav1-m, tav2-f, and more.
An actor with no entry stays silent. Whispers and choices are not voiced.
The emotion of a `say` line sets the style: happy, sad, blush -> warm; angry, shock -> tense; eyeroll -> wry; the rest -> neutral.
