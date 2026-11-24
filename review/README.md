# Video Review

A page on your Mac for reviewing a cut. Watch it, pause at the exact moment something is off, press **N** and type what to change. Claude reads the notes, fixes only those moments and writes back what it changed.

The same small server also runs the **Studio page** (the front door), the **Footage Log** pages and, once it's set up, the **Asset Library** page. It works on every video in your content folder (`content_root` in `studio.json`): raw clips, finished videos, style tests and older versions in every shoot folder.

## What's in this folder

| File | What it is |
|---|---|
| `review.py` | The server: Video Review, the Footage Log API, and the routes for the Studio and Asset Library pages. Standard library only. |
| `editor.html` | Video Review: the library of videos and the review page (player, beats, notes, timeline) |
| `studio.py`, `studio.html` | The Studio page and its API |
| `library.html` | The Footage Log pages: **Footage** and **Videos** tabs |

## Open it

Pick one:

- **Ask Claude:** "open the studio" or "open video review". Claude starts it in the browser pane (the `video-review` entry in `.claude/launch.json`).
- **Terminal**, from the kit folder:

  ```bash
  .venv/bin/python review/review.py
  ```

  It opens http://127.0.0.1:8765 in your browser. To open one video straight away, add its path after `review.py`. To review a different folder, give that folder instead. `--port N` picks another port, `--no-browser` doesn't open a window.

The port is `review_port` in `studio.json` (8765 unless you change it). If that port is busy, it takes the next free one and says which. If you change `review_port`, change the `port` in `.claude/launch.json` to match.

It only answers on this Mac (127.0.0.1). Nothing is uploaded anywhere.

## The pages

| Address | Page |
|---|---|
| `/studio` | The **Studio page**: the front door (below) |
| `/` | **Video Review**: every video, then one video at a time |
| `/library` | The **Footage Log**: Footage and Videos tabs |
| `/assets` | The **Asset Library** search page, once it's set up (`assets/README.md`) |

## Studio page

http://127.0.0.1:8765/studio is the front door to the whole studio. It greets you by name (`owner` in `studio.json`) and reads everything fresh each time it loads, so it never needs updating by hand.

- **Home:** big buttons for Start a new edit, Review a video, Footage, Videos, Assets, Glossary, Classroom, Ideas, Guides and What to say. Under them, **what needs you**: edits in progress, videos with open notes, videos in review and videos ready to post (from the notes files and the video tracker). At the bottom: what Claude does when you approve a video (`guides/after-approval.md`). If the house rules aren't there yet, it says to run the setup.
- **Edits:** the project cards. **Start a new edit** opens a card: title, brand (one button per folder in `brands/`), style (one per style in `STYLES.md`, Fast Cut once per skin; there's no default, so pick "Ask me" and Claude asks), the shoot folders and clip refs (paste them from the Footage tab's **Copy ref**), what the video is for, the script, length and platform, what to keep and avoid, classroom reels and effects you want, and a status. **Save card** (or Cmd+S) writes it to `../cards/`. Then tell Claude `start the card <name>`.
- **Glossary:** every effect (with its command, when it fits, whether it's approved or in review, a strip of frames and its preview), the styles, skins and Fast Cut layouts, the studio's own words and the tracker statuses. It's built from the files that define each one (`effects/catalog/`, the effects skill, `effects/README.md`, `STYLES.md`, `guides/glossary-words.md`, the video tracker), so to change what it says, change those files.
- **Classroom:** the editing references in `../classroom/` (reels saved for how they're cut), with tag filters.
- **Ideas:** the content references in `../ideas/` (reels saved for what they say), with tag filters.
- **Guides:** your guides first (storytelling, house rules, after approval, what to say, glossary words, each brand's guide and voice), then every README, shown as pages.
- **What to say:** every phrase Claude knows (`guides/what-to-say.md`), and every effect command. Click one to copy it.

The only files the Studio page writes are `../cards/<date>-<title>.card.json` (names are made from the date and title; anything else is refused).

## Video Review

- **Library:** the 8 most recently changed videos are at the top, with every folder below. Orange and green badges count the open and done notes.
- **Player:** click the video or press Space to play.
- **Beats:** one row per spoken line, with the words lighting up as they're said. They come from the video's transcript: a `.words.txt` file, or the video's `.srt`. With no transcript, each shot is a beat, and **Transcribe the speech** makes a transcript in a few seconds with whisper.cpp.
- **Timeline:** frames, beats, sound and notes. White lines mark the shot changes. Click or drag to move around. Zoom with **+**, **−** and **Fit**, or pinch on the trackpad.
- **On screen:** when a video has an effects map (`../effects/README.md`), a row between the ruler and the frames names what's on screen over each stretch: a Fast Cut layout (Split screen, Card, Big number, Punch-in…), a library effect (spotlight, arch-text…) or a graphic (hook title, tag, end card). Plain footage stays empty. Hover a block for what it is, click it to jump there; while it's on screen, the bar above the timeline names it, with a link to its Glossary entry. A note you add there records what was on screen.
- **Sound tracks:** when a video has a sound map (`../sound/README.md`, "Sound maps"), the sound shows as one row per track: voice, music (with the song's name), the footage's own sound and the sound effects. Each row is drawn at its level in the finished mix, so a quiet track looks quiet. Every sound effect is a block at its time and length; hover for its name, time and level, click it to jump there. **Tracks** and **One row** switch between the two views. A note you add while the playhead is on a sound effect records which one.
- **Notes:** each has its time, the line being spoken and your text. Click a note to jump to it, click its text to edit it, and **Open / ✓ Done** switches its status. Claude's replies show under each note as soon as Claude writes them.

### Keys

| Key | Does |
|---|---|
| Space or K | Play / pause |
| N | New note at this moment (Enter saves, Shift+Enter is a new line, Esc cancels) |
| ← → | Back / forward 1 second (hold Shift for 5) |
| , . | Back / forward 1 frame |
| [ ] | Previous / next beat |
| + − Z | Zoom in, zoom out, fit the whole video |

## Footage Log pages

**Footage log & video tracker →** at the top of the library (or http://127.0.0.1:8765/library) opens two tabs:

- **Footage:** every raw clip and its moments. Search what happens, what's said or a tag; filter by shoot, camera (the `Raw/` subfolder), person or tag; or show only moments that haven't been used yet or have no flags. **Open** plays the raw clip from that second; **Copy ref** copies something like `C0041.MP4 0:09.7–0:13.9 (2026-03-14 Kitchen Remodel)` to paste to Claude or into a card.
- **Videos:** every finished video, style test and older version by shoot, with its status, posted date, link and notes (changes save straight away) and the raw seconds it used.

The data comes from `<content>/Footage Log/` (`../library/README.md`).

## Where things are saved

- **Notes:** `<video file>.notes.json`, next to the video. For example `Kitchen-Reveal-v2.mp4.notes.json`. Never delete one.
- **Transcripts:** `<video file>.words.txt`, next to the video (the Footage Log's format).
- **Sound maps:** `<video file>.sound.json`, written by `../sound/soundmap.py`. This page only reads them; delete one and the video goes back to one sound row.
- **Effects maps:** `<video file>.effects.json`, written by `../effects/effectsmap.py`. This page only reads them.
- Both maps are written by themselves when an export is put in its shoot with `../library/finish.py`, from the record the builder kept. `footage.py index` makes any that are missing.
- **Frames, sound and shot changes:** a cache in `~/.cache/video-review`. It's safe to delete; it rebuilds itself.

## For Claude: applying notes

When you're told "apply my notes on <video>":

1. Read `<video>.notes.json` next to that video. Work only on notes with `"status": "open"`. Each note has `t` (seconds into **that file**), `timecode`, the `beat_text` being spoken there, and the owner's `text`.
   - **Notes on a sound effect.** On a video with a sound map, a note made while the playhead was on a sound effect also has `sfx`: a list (usually one) of the effects playing there, each with `name`, `what` (the kind: whoosh, pop, chime…), `file` (the sound's file), `t` and `len` (where it starts and how long it plays, in this file's seconds), `at` (Real SFX's own cue time) and `i` (its place in the map's effects list). So "cut this one" means that effect. The map (`<video>.sound.json`) names the Real SFX run in `cues_from`. From `~/.claude/skills/real-sfx`, change that cue with `python3 scripts/sheet.py set <run folder>/cues.json --at <at> KEY=VALUE`, or take it out with `sheet.py drop … --at <at>` (add `--label` when two cues sit within 30 ms), then run `mix.py` again, export the new version and make its sound map (`../sound/README.md`). Notes without `sfx` are about the picture or the mixed sound.
   - **Notes on a visual effect.** On a video with an effects map, a note made while something was on screen also has `on_screen`: a list (usually one) of what was there, each with `label` (as the row shows it), `entry` (its Glossary name, when it has one), `detail`, `t` and `len` (where that stretch starts and how long it lasts) and `i` (its place in the map's `blocks`). So "remove this effect" means that one. The map (`<video>.effects.json`) lists in `made_from` the build record it came from: change that scene's layout, effect or graphic in the builder's script or spec, export the new version, and the maps come with it.
2. Map `t` back to the edit: find the shot in the builder's script or spec (or its build record, `<render>.build.json`) that covers that time. Fix **only** what the note asks, and leave everything else alone.
3. Export a new version next to the old one (`v2`, `v3`…) with `../library/finish.py`. Never overwrite the file the notes point at, because their timestamps belong to it.
4. In the old video's notes file, set each fixed note to `"status": "done"`. Write one short line in `"reply"` saying what changed (for example "Trimmed 0.4 s of pause before this line"), and put the new file's name in `"done_in"`. If you couldn't do a note, leave it open and say why in `"reply"`. Edit the JSON in place and keep the other fields. The page picks the changes up within about 4 seconds.
5. Say the new file's name. It shows at the top of the library under Recently changed.

## How it's built

`review.py` is one standard-library server. It loads `studio.py` the first time a `/studio` page or `/api/studio/` call is asked for, and `../assets/browser/serve.py` the first time `/assets`, `/assets/data` or `/assets/thumb/<name>` is asked for (it calls that module's `handle(handler, method, url)`), so nothing else depends on either. POST requests need the `X-Video-Review: 1` header the pages send, and any request whose Host isn't 127.0.0.1 or localhost is refused. Settings come from `../lib/studio_config.py`; set `STUDIO_CONFIG=/path/to/other.json` to run it against another settings file (tests do this).
