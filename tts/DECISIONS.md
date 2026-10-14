# Voice narration: what we tried and why

Goal: the DM narration speaks in real time. Best result: the Baldur's Gate 3 narrator voice. Acceptable result: a realistic, emotional voice that follows punctuation. Robotic voices are not acceptable.

This is for personal, local use. Do not share the game audio or any voice made from it. The F5-TTS weights are CC-BY-NC.

## How it works

1. The DM writes a beat. `@narrate[ominous] text` and `@say[emotion] <actor> text` are voiced.
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

| Mood | Cluster | User note | Clips (the service picks one per line) |
|---|---|---|---|
| neutral | – | bench clip, picked by hand | `Here the chaos of the world is dimmed…` |
| ominous | 1 | dark, menacing | p0012, p0194, p0568, p0854, p0971, p1393, p1869, p1911 |
| warm | 3 | soft, inner thought, compassion | p0454, p0855, p2015, p2186, p0286 |
| wry | 4 | curious, playful, sensual | p0081, p0116, p1132, p1325, p0381, p1353 |
| tense | 8 | uncertain, nervous | p1524, p0099, p2120, p0335, p1245 |
| intense | 7 | slow, low, intense | p0060, p0795, p1243, p1045, p0670, p1091 |
| urgent | 5 | needs fast attention | p0028, p0505, p1389, p0865, p1735, p2070 |
| action | 10 | fast, describing action | p0143, p0317, p1757, p1111, p0177 |
| bright | 9 | joyful, discovery | p1157, p0381, p2080, p0699, p1990 |
| somber | 6 | narrative, slightly down | p0556, p1388, p0447, p0180, p2184 |


The first pick was one clip per mood. The user then ticked several clips per mood on a page (`tts/tools/14_mood_variants.py`), because one clip made every line of a mood sound alike. Wry and ominous changed most: the first wry clip sounded grave, and the first ominous clip was too fast. Candidates were the clips nearest to the kept ones in the same cluster. Clip ids come from `~/bg3voice/picker/narrator/pool.json`. `~/bg3voice/voices` is not in git, so this table is the only record.

## How the actor emotions were chosen

1. We first clustered the actors' clips on prosody, as for the narrator, for four key actors and then across all voices. The clusters did not give distinct emotions: they were balanced across speakers and the user could not hear a clear emotion in them. Dialogue differs from narration, so the narration moods did not apply.
2. We switched to pretrained emotion models (no manual labels): emotion2vec_plus_large (audio class, FunASR model licence, read once), audeering wav2vec2 (arousal, valence, dominance; CC-BY-NC-SA-4.0) and distilroberta (text class). The score is 0.6 audio plus 0.4 text, with gates on arousal, valence and dominance as a tie-breaker. Audio and text agree on the top class for only 28 percent of clips, and the text model says "neutral" for most lines. So the audio model leads.
3. We use the model labels for the DM: neutral, happy, angry, sad, surprised, fearful, disgusted. The old nine names came from the portrait faces. They had no model class (shame, blush, closed) or were split by the model (shock into surprised and fearful, eye-roll into disgusted). The portrait face follows the emotion.
4. For each actor and emotion the tool ranks 3 clips. The user checked them on a QA page and found that almost always one of the 3 fits. `13_emotion_apply.py` installs them.

## Mood tag and emotion table

- `@narrate[mood] text` sets the narrator style. Valid moods: `stage/beat.py` (`MOODS`). The DM skill (`game/.claude/skills/stage/SKILL.md`) lists the same moods. A test checks that both agree.
- `@say` emotion is the voice style. There are seven: neutral, happy, angry, sad, surprised, fearful, disgusted (the labels of the emotion models). The portrait face follows the emotion in `stage/lpc.py` (`EMOTION_FACES`): surprised and fearful use the shock face, disgusted the eye-roll face. The art has no separate faces for them. A voice without a clip for the style falls back to neutral.
- Narration moods and dialogue emotions are two lists on purpose. A narrator delivers a mood. An actor delivers an emotion. One service field (`style`) carries both. A voice library holds the labels that fit its kind.
- A mood or emotion can hold several reference clips (`<label>.2.wav`). The service picks one per line from a hash of the text.
- Only voices listed in `<campaign>/stage/voices.json` speak `@say` lines. See `stage/voices.example.json`. An actor that is not listed gets a default: the library voice with its own id, else a generic `tav` voice picked by the `body` in its actor file (`voice.default_voice`). An actor with no actor file stays silent. Whispers are never voiced.

## What lives in `~/bg3voice` (not in git)

| Path | Content |
|---|---|
| `wav/`, `norm/24k/`, `kept.tsv` | narrator clips, normalized, with text |
| `actors/data/<slug>/` | per actor: `refs/`, `train/`, `heldout/` (the clip pool for the picker) |
| `picker/<slug>/` | picker page, generated test lines, notes |
| `voices/<slug>/<mood>.wav + .txt` | the voice library the service reads |
| `voices_old/` | backups of replaced clips |
| `bench/` | model bake-off scripts and venvs |

To rebuild: run `tts/tools/01` to `03` for the narrator, `07` for the actors, `08` for the library of actors, then make the narrator pool with `09`, tick moods with `14`, and make actor emotions with `13`. The tools need the BG3 install on Windows. See `tts/README.md`.

## Known gaps

- The service has no authentication. It binds to `127.0.0.1`. A bind for the Raspberry Pi needs a firewall rule or a token.
- The Pi cannot run TTS. Point `DUNGEON_TTS_URL` (or `tts_url` in `game/settings.json`) at the PC. With no URL the game is silent. Menu > Settings > Narration voice switches the voice off for the whole server, even when a URL is set (`voice` in `game/settings.json`, default on).
- No full test in a live game. The browser playback and the crackle fix are not confirmed by ear.
- The first line after a long pause can take up to about 2 seconds.
- The audio cache has no size limit (about 10 MB now).
- Fearful and surprised clips are rare. Every actor has some emotion with fewer than 8 eligible clips. The user checked the picks on the QA page but has not heard them in a live game.
