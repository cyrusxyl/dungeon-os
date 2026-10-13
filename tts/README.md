# DungeonOS narration TTS

Separate uv project. Do not add torch to the root project.

## WSL quick start
The `.venv` must hold the gpu extra (`uv sync --extra gpu`, done once).

1. Start the service: `tts/run.sh` (real voice, F5 on CUDA). Use `tts/run.sh mock` for test tones.
2. Wait for the model to load. Then check it: `curl http://127.0.0.1:8770/health`. It lists the voice slugs.
3. Set `"tts_url": "http://127.0.0.1:8770"` in `game/settings.json`.
4. Map actors to voices in `game/campaigns/<campaign>/stage/voices.json`. Keys are actor ids. Values are slugs from `/health`.
5. The player character speaks only if its id is in `voices.json` and the player voice option is on. The option is in Settings.
6. Stop the service: `pkill -f "uvicorn service.app:app"`.

You can also start it from Settings, on the Voice tab. Set the service URL to this machine (for example `http://127.0.0.1:8770`), save, then press Start voice server. The stage server runs `tts/run.sh f5` and writes the log to `tts/cache/service.log`. It stops only a service it started. It keeps that service running when it exits, unless you tick "Stop it when the game server stops". Set `DUNGEON_TTS_ENGINE=mock` for the stage server to start the mock engine.

## Share the voice with another machine (the Pi)
Run `uv run dungeon-voice` on this machine. It starts the service and opens a reverse SSH tunnel to the host `pi` (an `ssh` host name). The Pi then reaches the voice at `http://127.0.0.1:8770`. This needs no firewall rule. It works while the command runs on this machine. The tunnel reconnects after a drop. Stop it with Ctrl+C.

On the Pi, set `"tts_url": "http://127.0.0.1:8770"` in `game/settings.json`. The Pi has no `tts/.venv`, so its Settings page shows no Start button.

Options: `--tunnel "host1 host2"` (or `DUNGEON_VOICE_TUNNEL`; empty means no tunnel), `--engine mock`, `--port`.

`tts/run.sh` reads `TTS_PORT`, `TTS_HOST`, `TTS_VOICES_DIR` and `BG3_VOICE_HOME`.

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
- `13_emotion_scores.py`, `13_emotion_qa.py`, `13_emotion_apply.py`: actor emotion references from pretrained models (see below).
- `14_mood_variants.py`: several reference clips per narrator mood (see below).

## Voices for NPCs
Narration uses the `narrator` voice. A `say` line is voiced only if its actor has a voice.
Write the map in `<campaign>/stage/voices.json`. See `stage/voices.example.json`.

    {"innkeeper": "minsc", "villain": "emperor"}

Keys are actor ids. Values are voice slugs. A slug is a folder name in the voice library:
narrator, astarion, shadowheart, laezel, gale, karlach, wyll, halsin, minthara, jaheira, minsc, emperor, tav1-m, tav2-f, and more.
An actor with no entry stays silent. Whispers and choices are not voiced.
The emotion of a `say` line is the voice style. A voice with no clip for the style falls back to neutral.

## Narrator moods with several clips
A mood can hold more than one reference clip: `ominous.wav`, `ominous.2.wav`, and so on (each with a `.txt`). The service picks one clip per line from a hash of the text. The same line always gets the same clip, so the cache stays valid.

    ~/bg3voice/venv_emo/bin/python tools/14_mood_variants.py gen      # test line for each candidate (service must run)
    ~/bg3voice/venv_emo/bin/python tools/14_mood_variants.py serve    # http://127.0.0.1:8797/variants.html
    ~/bg3voice/venv_emo/bin/python tools/14_mood_variants.py apply    # install the ticked clips

Tick every clip that fits a mood. A mood with fewer than 5 ticked clips gets 5 new candidates when you run `gen` again. Candidates come from the narrator pool that `09_ref_picker.py` makes (`~/bg3voice/picker/narrator/pool.json`).

## Emotion picks from pretrained models (no manual labels)

Use the venv `~/bg3voice/venv_emo`. Run `export HF_HOME=~/bg3voice/emotion/hf` first.

1. `python 13_emotion_scores.py` scores all pool clips (`~/bg3voice/emotion/pool.json`: id, actor, path, text, dur) with emotion2vec_plus_large (audio class), the audeering wav2vec2 dim model (arousal, dominance, valence; CC-BY-NC-SA-4.0) and distilroberta (text class). It caches `~/bg3voice/emotion/scores.parquet`, then writes `picks.json` (3 candidates per actor and emotion) and `report.txt`. The formula is in the file docstring.
2. `python 13_emotion_qa.py` serves `http://127.0.0.1:8796/`. Mark each pick good or bad, cycle alternatives, add notes. Saved to `qa.json`.
3. `python 13_emotion_apply.py --dry-run`, then without the flag. It installs `<emotion>.{wav,txt}` for all seven emotions. It backs up to `~/bg3voice/voices_old/`.

Emotions use the model labels: neutral, happy, angry, sad, surprised, fearful, disgusted.
Each score is 0.6 audio plus 0.4 text. Surprised, fearful and disgusted use gates on arousal, valence and dominance (percent rank inside the actor). The gates are in the file docstring.
