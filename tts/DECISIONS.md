# Voice narration: what we tried and why

Goal: the DM narration speaks in real time. Best result: the Baldur's Gate 3 narrator voice. Acceptable result: a realistic, emotional voice that follows punctuation. Robotic voices are not acceptable.

This is for personal, local use. Do not share the game audio or any voice made from it. The F5-TTS weights are CC-BY-NC.

## How it works

1. The DM writes a beat. `@narrate[ominous] text` and `@say <actor> <emotion> text` are voiced.
2. The stage server finds the line by its sequence number. It sends `text`, `voice` and `style` to the TTS service. The path is `GET /api/tts/line/{seq}`.
3. The TTS service (`tts/service`, port 8770) splits the text into sentences. F5-TTS speaks each sentence with a reference clip. Audio streams back as raw PCM16, 24 kHz, mono.
4. The browser plays the stream (`stage/web/src/lib/voice.ts`).
5. If the service is off, the stage server returns 204 and the game stays silent.

The stage server also sends `POST /warm` for new lines. The service then makes the audio before the player reads the line. A live request goes before any warm job.

## Model choice

All models ran on an RTX 5080 (16 GB) with torch cu128. The test used one 9-second narrator clip and 8 test lines. We could not judge quality by script. The user listened.

| Model | RTF (lower is faster) | VRAM | Word error |
|---|---|---|---|
| F5-TTS v1 Base | 0.17 | 0.8 GB | 0% |
| Chatterbox | about 0.6 | 3.6 GB | 0% |
| GPT-SoVITS v4 | 0.69 | 2.3 GB | 1.9% |
| GPT-SoVITS v5 | 0.6 to 1.1 | 2.2 GB | 5 to 6% |
| Qwen3-TTS 1.7B | 1.94 (no flash-attn) | 4.5 GB | 0% |

The user chose F5-TTS. It had the best voice quality and emotion. It was also the fastest. The F5-TTS weights are non-commercial, which is fine for this use.

## Where the voice data comes from

- The narrator is the actor `vNARRATOR` in `Localization/Voice.pak`. It has 7,629 clips (14.7 hours).
- Other actors use a UUID in the file name: `v<UUID>_h<handle>.wem`. The user named 19 of them by listening (`tts/tools/actors.json`).
- UUID `ee6ed7…` is a shared spell-chant and insult voice. It has too few full sentences. We skipped it.
- Tools: LSLib `Divine.exe` unpacks the pak. `vgmstream-cli` converts `.wem` to wav. The text of each line is in `english.loca`. The handle in the file name is the key.
- Whisper large-v3 checks each clip against its text. It dropped 11.9% (874 clips). 6,481 clips (12.4 hours) stay.

## What we tried and dropped

**Fine-tuning F5-TTS.** We trained on 392 clips (45 minutes), learning rate 1e-5, 2,394 updates. Word error stayed flat. Speaker similarity rose from 0.794 to 0.827. The user heard no consistent gain. One note: the saved EMA weights barely moved, because F5 resumes from the pretrained step count (1.25 million). We used the raw weights. We dropped fine-tuning. Zero-shot is good enough, and a new voice costs only a reference clip.

**Heuristic reference clips.** The first library used a formula on pitch, loudness, rate and pauses. "Neutral" was the most average clip, so it was flat and fast. F5 copies the pace and mood of its reference, so the output was flat and fast. A hand-picked slow, dramatic clip sounded better.

**Retrieval of references by text similarity.** For each text we searched the voice's own lines (MiniLM embeddings) and used the closest line as the reference. It matched topic, not mood. Text sentiment is not delivery. The user judged it not worth the complexity. We removed it.

**Streaming and step count.** 16 steps and 32 steps sound the same to the user. We use 16 (faster). Streaming and whole-sentence output also sound the same.

**Crackle in the browser.** The audio context ran at the device rate (48 kHz). Each 0.2-second 24 kHz buffer was resampled alone, and each edge clicked. Fix: `new AudioContext({ sampleRate: 24000 })`. The test page and the game client both use it. The user has not yet confirmed the fix by ear.

## How the narrator moods were chosen

1. We pooled 2,191 narrator clips (6 to 10 s, word error 0, plain text).
2. We clustered them with k-means on 4 features: pitch variation, loudness variation, speaking rate, pause share. Loudness mean and median pitch were dropped (correlated or weak).
3. The silhouette score is about 0.17 for k = 6 to 14. The data is a continuum, not clean groups. We used k = 10.
4. The user listened to 5 clips per cluster and wrote a note for each (`tts/tools/09_ref_picker.py` made the page).
5. We mapped notes to moods. For each mood, F5 made test lines from each of the 5 candidates. We measured the same 4 features on the output. The candidate closest to the cluster profile won. A clip with a fan-only name lost to a close alternative.

| Mood | Cluster | User note | Clip |
|---|---|---|---|
| neutral | – | bench clip, picked by hand | `Here the chaos of the world is dimmed…` |
| ominous | 1 | dark, menacing | p0296 |
| warm | 3 | soft, inner thought, compassion | p0454 |
| wry | 4 | curious, playful, sensual | p1632 |
| tense | 8 | uncertain, nervous | p1524 |
| intense | 7 | slow, low, intense | p0060 |
| urgent | 5 | needs fast attention | p0028 |
| action | 10 | fast, describing action | p0143 |
| bright | 9 | joyful, discovery | p1157 |
| somber | 6 | narrative, slightly down | p0556 |

Clip ids come from `~/bg3voice/picker/narrator/pool.json`. `~/bg3voice/voices` is not in git, so this table is the only record.

## Mood tag and emotion table

- `@narrate[mood] text` sets the narrator style. Valid moods: `stage/beat.py` (`MOODS`). The DM skill (`game/.claude/skills/stage/SKILL.md`) lists the same moods. A test checks that both agree.
- NPC voices have only five styles (neutral, ominous, tense, warm, wry). A missing style falls back to neutral.
- `@say` emotion maps to a style in `stage/voice.py` (`STYLES`): happy to bright, angry to intense, sad and shame to somber, shock to urgent, blush to warm, eyeroll to wry, neutral and closed to neutral.
- Only voices listed in `<campaign>/stage/voices.json` speak `@say` lines. See `stage/voices.example.json`. An unmapped actor stays silent. Whispers are never voiced.

## What lives in `~/bg3voice` (not in git)

| Path | Content |
|---|---|
| `wav/`, `norm/24k/`, `kept.tsv` | narrator clips, normalized, with text |
| `actors/data/<slug>/` | per actor: `refs/`, `train/`, `heldout/` (the clip pool for the picker) |
| `picker/<slug>/` | picker page, generated test lines, notes |
| `voices/<slug>/<mood>.wav + .txt` | the voice library the service reads |
| `voices_old/` | backups of replaced clips |
| `bench/` | model bake-off scripts and venvs |

To rebuild: run `tts/tools/01` to `03` for the narrator, `07` for the actors, `08` for the library of actors, then choose clips with `09` and install them with `10`. The tools need the BG3 install on Windows. See `tts/README.md`.

## Known gaps

- The service has no authentication. It binds to `127.0.0.1`. A bind for the Raspberry Pi needs a firewall rule or a token.
- The Pi cannot run TTS. Point `DUNGEON_TTS_URL` at the PC.
- No full test in a live game. The browser playback and the crackle fix are not confirmed by ear.
- The first line after a long pause can take up to about 2 seconds.
- The audio cache has no size limit (about 10 MB now).
- Only the narrator has the 10 moods. Actors have the five heuristic ones, and the user has not checked them.
