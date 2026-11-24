# Styles

The builders for the three named styles, the reel-cover maker and the sample sheets. What each style looks like and its rules are in `../STYLES.md`; this page is what's in the folder and how to run it.

Commands are written for the kit's Python (`.venv/bin/python`, made at setup), run from the kit folder.

## What's here

| Path | What it is |
|---|---|
| `fastcut/engine.py` | The Fast Cut engine: an edit (pieces of clips end to end), scenes that change the layout every 1–2 s, captions from the transcript, effects, sound, the sound-effect moments and the build record. |
| `fastcut/graphics.py` | Fast Cut's animated pieces: `Hook`, `ListPanel` (split-screen panels), `Checklist`, `StatCard` (cards), `BigNumber`, `Compare`, `Slam`, `Mosaic`, `EndCard` (full screen). |
| `fastcut/skins.py` | The **Dark** skin and the **Brand** skin (everything from `brands/<slug>/brand.json`). |
| `fastcut/example.py` | One Fast Cut reel from any talking clip and B-roll, laid out from what's said. The pattern for writing a real one. |
| `talking-head/reelkit.py` | The Talking Head Classic builder: shots, sound pieces cut in pauses (`phrase()`), the title box, labels, word-by-word captions, effects, the build record. |
| `talking-head/example_reel.py` | One Talking Head Classic reel from any talking clip (and a B-roll clip). |
| `talking-head/verify.py` | Re-transcribes a finished video and lists every word that differs from the plan; checks each cut lands in a pause. Works on any builder's video. |
| `hands-on/build_reel.py` | The Hands-On Classic builder: a reel from a JSON edit spec, graded and drawn in the brand's look. `--starter` writes a spec from a shoot's clips. |
| `hands-on/handson_graphics.py` | Its graphics: hook, captions, tags, lower third, counter, end card. |
| `hands-on/SPEC.md`, `hands-on/example-spec.json` | Every spec field, and a full example for the demo shoot. |
| `cover.py` | A reel cover (1080 × 1920 JPG) from a frame, in the Dark look or the brand's, with an optional pop-out. |
| `make_samples.py` | One contact sheet per style and skin, from whatever clips are in a folder. |
| `person_mask.swift` | Finds the person in a frame (Apple Vision, built into macOS): crops follow them, covers pop them out. |
| `stylekit/` | Shared pieces: `paths` (shoots, clips, safe output names), `media` (ffmpeg, crops, graded clips, the subject finder), `draw` (Pillow drawing), `words` (transcripts, captions, cut points), `audio` (sound runs, music, loudness), `fit_music.py` (fits a track to a length), `record` (build records), `fxhook` (the effects library). |

Work and cache folders (`<style>/work/`, `<style>/cache/`, or under `work_dir` in `studio.json`) can be deleted any time; they're out of git.

## Run them

```
# Fast Cut (Dark skin by default; --skin brand for the brand's)
.venv/bin/python styles/fastcut/example.py --footage "<shoot>" --sheet          # one frame per scene, under a minute
.venv/bin/python styles/fastcut/example.py --footage "<shoot>" --plan           # the scenes, rhythm notes, text nobody said
.venv/bin/python styles/fastcut/example.py --footage "<shoot>"                  # the full render
.venv/bin/python styles/fastcut/example.py --footage "<shoot>" --skin brand --effect "todo@3-7" --music "my-track.wav"

# Talking Head Classic, then check its words
.venv/bin/python styles/talking-head/example_reel.py --footage "<shoot>" --title "Three things nobody tells you"
.venv/bin/python styles/talking-head/verify.py "<shoot folder>/Style Tests/<name>_v1.mp4"

# Hands-On Classic
.venv/bin/python styles/hands-on/build_reel.py styles/hands-on/example-spec.json
.venv/bin/python styles/hands-on/build_reel.py --starter "<shoot>" > my-reel.json

# A cover, and the sample sheets
.venv/bin/python styles/cover.py "<video>" --at 3.2 --title "THE BIG|IDEA" --skin brand
.venv/bin/python styles/make_samples.py --footage "<shoot>/Raw" --out "<shoot>/Style Tests/Samples" [--brand my-brand]
```

`--footage` takes a shoot name (`"2026-03-14 Kitchen Remodel"`), a shoot folder, its `Raw/` folder or any folder of clips. A clip needs a transcript (`<clip>.words.txt`, made by the Footage Log); the builders make one with `whisper-cli` if it's missing.

## What every builder does

- Writes the video to `<shoot>/Style Tests/<name>_vN.mp4`, never over an existing file (`--out` puts it elsewhere, and refuses an existing name too).
- Writes `<video>.words.txt` (every word the video should say, for `verify.py`), the build record in its work folder (`work/<name>/<video>.build.json` and the separate sound tracks), and the video's sound and effects maps beside it, so Video Review's rows fill in by themselves. A line starting `[build record]` says what happened; a problem there never touches the video.
- Records the raw seconds it used, so the Footage Log knows what each video used.
- Writes the sound-effect moments to `work/<name>/sfx_events.json` for the sound-effects pass (`sound/README.md`).
- Takes visual effects from the effects library (`effects/fx.py`) and puts them on the picture before the captions.
- Cuts sound only in pauses found in the sound level, and keeps every piece a whole number of frames.

## Settings and brand fields used

| Where | Key | Used for |
|---|---|---|
| `studio.json` | `content_root` | Shoots and where videos go. |
| `studio.json` | `default_brand` | The Brand skin and Hands-On Classic when no brand is named. |
| `studio.json` | `music_library` | Where `--music` / `music_file` look for a track by name. |
| `studio.json` | `whisper_model` | Optional. The whisper.cpp model for transcripts and `verify.py` (default `~/.cache/whisper.cpp/ggml-base.en.bin`). |
| `studio.json` | `work_dir` | Optional. Where work and cache folders go (default: inside each style's folder). |
| `brand.json` | `colors` (background, surface, text, muted, accent, highlight, good, bad), `fonts` (title, heading, caption, number, body), `captions`, `grade`, `logo`, `name`, `handle`, `end_card_line`, `keep_out` | The Brand skin, Hands-On Classic and covers. |

## What to say to Claude

- "Make this a **Fast Cut**" / "**Fast Cut, Brand skin**" / "in **Talking Head Classic**" / "in **Hands-On Classic**".
- "Show me a sheet first": the `--sheet` contact sheet before a full render.
- "Check the words": `verify.py` on the latest version.
- "Make a cover for this one": `cover.py`.
- "Make the style samples from this shoot": `make_samples.py`.
