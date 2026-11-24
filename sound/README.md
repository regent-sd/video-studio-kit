# Sound effects

Every new video and every re-edit gets a sound-effects pass by default, without being asked. Claude adds effects only where they make sense, then lists what went in so you can cut any of them in Video Review.

## What's in this folder

| File | What it is |
|---|---|
| `soundmap.py` | Saves a finished video's separate sound tracks beside it (`<video>.sound.json`), so Video Review's timeline shows voice, music, footage sound and every sound effect on their own rows |
| `README.md` | This page: when effects make sense, how the pass runs, sound maps |

## Where the sounds come from

| Source | What it is | Where |
|---|---|---|
| **Your sound library** | Real recordings: whooshes, risers, hits, pops, clicks, ticks, chimes, paper, typing, plus the sounds of your own world (tools, kitchen, machines, ambience). Start with a free CC0 set; add packs you buy. | `sound_library` in `studio.json` (default `~/Music/Sound Effects`). How to build it: `../setup/SOUND-LIBRARY.md` |
| **uisfx** | 78 small CC0 interface sounds that come with Real SFX | inside the Real SFX skill |
| **Earshot bank** | Sounds made in code. A fallback only, when the real recordings have fewer than three sounds that fit a moment. | a fallback folder in your sound library, if you rendered it |
| **Openverse** | A free search of CC0 and Creative Commons sounds, for anything the library lacks | `https://api.openverse.org/v1/audio/?q=WORDS&license=cc0` |

The tools:
- **Real SFX** (`~/.claude/skills/real-sfx`): places real sounds on the exact frame, keeps the voice and music, and writes a new MP4 plus a separate effects track.
- **Earshot** (`~/tools/earshot`, the `earshot` skill and MCP server): listens for Claude. It describes, matches and ranks sounds and checks a finished mix. Claude can't hear, so it never judges sound by guessing.

## When effects make sense

- **Something on screen causes every sound:** a new layout, a card or tag appearing, a counter, a slam, a check mark, the hook title, the end card.
- **Not on every cut.** Talking-head jump cuts get nothing. Heavy hits go on at most a third of the cuts.
- **Real sound in the footage wins.** Never lay a library sound over a shot that already makes that sound (a pour, a machine, a knock). Library foley only goes under shots that are silent or muted under music.
- **Loud enough to notice, under the voice.** Effects sit about **6–8 dB under the voice**. At Real SFX's default level they sit nearer 19 dB under and most go unnoticed, so the default here is `--voice-depth light --sfx-trim-db 8`. That puts the critique's `audibility` median at about −5 to −6 dB. Don't go much past it.
- **Never on a word.** Effects duck while you talk (`--voice-safe`), and none may come within 3 dB of a word (the critique's `speech` score must pass). An effect never lands on the start of a word.
- **With music,** put effects on the beat where possible and never add a rhythm of their own.
- **Leave quiet moments quiet:** a reveal, a first taste, a reaction, the room sound of a payoff shot.
- **Variety:** the same file never plays twice in a row.
- **List them in the hand-off.** Say in a line or two which effects went in and where, so you can cut any of them.

## By style

- **Fast Cut:** the moments the script already knows get real recordings: a whoosh into each card scene, pops for tags, ticks for counters, a hit for slams, a chime for check marks. The builder writes these moments to `work/sfx_events.json` and renders without an effects layer of its own, then the pass below adds the real ones.
- **Talking Head Classic:** light touches only: a whoosh or hit on the title box, a hit on a big statement or number, a riser into the payoff. Jump cuts and B-roll with its own sound get nothing.
- **Hands-On Classic:** the room's own sound stays up front. Effects go only where the picture is silent: the hook title, text pop-ins, the end card. A muted montage under music can get light foley (a tap, a pour) when it helps.
- **A brand set to `restrained`** (`brands/<brand>/brand.json`, `effects.restrained`): fewer and softer effects, the same way as Hands-On Classic.

## How to run the pass (for Claude)

1. Render the video as usual, but without any effects layer of the builder's own. Keep that render in the work folder: it is the version without effects.
2. Write the moments to an event list, `work/sfx_events.json`. The builder knows them (the scene list, the card and tag times); for a video without a list, write it from the frames. Format: a JSON list of `{"t": seconds, "type": "whoosh", "len": 0.4, "g": 1.0}`. Types: `whoosh`, `wipe`, `hit`, `thump`, `riser`, `drop`, `pop`, `click`, `tick`, `chime`, `success`, `key` (typing; add `len` and `n`), `camera`, `water`, `glass`, `ambience`. The full table is in the Real SFX skill's `references/typed-cues.md`.
3. Run Real SFX from its folder (quote paths with spaces):
   ```
   cd ~/.claude/skills/real-sfx
   python3 scripts/from_cues.py WORK/sfx_events.json --video RENDER.mp4 --out WORK/sfx/cues.json --from-library chime
   python3 scripts/mix.py WORK/sfx/cues.json --out WORK/sfx/NAME_sfx.mp4 --voice-safe --voice-depth light --sfx-trim-db 8 --target-lufs -14 --ceiling-db -1.5
   python3 scripts/critique.py WORK/sfx/NAME_sfx_resolved_cues.json WORK/sfx/NAME_sfx_sfx_track.wav
   ```
   Add `--snap-beats` to `mix.py` when the video has music. With `--from-library chime`, quick interface sounds (pops, ticks, clicks) come from uisfx, which varies them across a run, and chimes and everything else come from your library. (`--ui library` takes pops from your library too; use it once the library has plenty of them.)
4. Read the critique and fix its three worst problems, then run `mix.py` and `critique.py` again until it says **PASS** (every score 8 or higher; expect about three rounds). Change one cue with `python3 scripts/sheet.py set WORK/sfx/cues.json --at SECONDS KEY=VALUE`. Common fixes:
   - **A hit piles onto the voice's bass (`low_end`):** `highpass=220 gain_db=-4`, and lower it more if the critique still asks.
   - **An effect on top of a word (`speech`):** `critique.py ... --list` names every one; lower each by the amount it gives (`gain_db=-6`). When two cues sit at the same time, pick one with `--index N`.
   - **A thin hit (`hierarchy`):** `gain_db=6`.
   - **The same file repeats (`variety`):** let uisfx take the pops (above), or add sounds to the library.
   The skill's `SKILL.md` has the full loop. Every louder step brings a few effects onto words, so expect to trim 3 to 5 per video.
5. Listen with Earshot: `~/tools/earshot/.venv/bin/earshot timeline WORK/sfx/NAME_sfx.mp4` lists what happens when. Confirm the voice still reads at about −14 LUFS and nothing clips.
6. Keep the render without effects and Real SFX's own files (`NAME_sfx.mp4`, `NAME_sfx_sfx_ducked.wav`, `NAME_sfx_resolved_cues.json`) in the work folder, so the effects can be turned down or off without a new render, and so the sound map can check the video against them.
7. Put the version with effects in its shoot with the finishing step:
   ```
   .venv/bin/python -I library/finish.py WORK/sfx/NAME_sfx.mp4 "<shoot>/Style Tests/<video name>-v1.mp4"
   ```
   It refuses if a file of that name is already there (a new version always gets a new name), then writes both maps beside the video: the **sound map** (voice, music with the song's name, footage sound, every sound effect) and the **effects map** (what's on screen over each stretch). They come from the build record the builder kept when it rendered (`../library/README.md`, "Build records"), so there is nothing to type. Last it refreshes the video tracker. If a map can't be made it says why in one line; the video stays in place.
8. If a file reached the shoot another way, `footage.py index` (run after every export anyway) notices the missing maps and makes them, or lists the videos it couldn't do and why.
9. In the hand-off, say which effects went in and where, for example "whooshes into the 4 card scenes, pops on 6 tags, a hit on 'finally' at 0:28".

**"No effects"** on a video: export the render without effects. **"Quieter effects":** run `mix.py` again with `--sfx-trim-db 5`. **"Louder effects":** `--sfx-trim-db 10`, then fix whatever the `speech` score lists.

## Sound maps (separate tracks in Video Review)

`soundmap.py` saves a small file beside a finished video, `<video file>.sound.json`, with the waveform of each track and the list of sound effects. Video Review's timeline then shows one row per track: the song's name on the music row, and every effect as a block at its time and length (hover for its name, time and level; click to jump to it). The level is the effect's loudest point in dB below full scale, as Real SFX placed it, before it ducks under the voice. **Tracks** and **One row** in the timeline bar switch between the separate tracks and the mixed sound. Videos without a map show one mixed row.

**From the build record (the usual way).** Builders keep a record of each render (`../library/buildrecord.py`): what's on screen over each stretch, the song (its file and name), and small copies of each sound track at its level in the mix in `<render>.tracks/` (one channel, 8 kHz: enough to draw and check, not to listen to). `finish.py` and `footage.py index` make the map from it:

```bash
.venv/bin/python -I sound/soundmap.py "<content>/<shoot>/Style Tests/<Name>-v1.mp4"          # --auto is the default
.venv/bin/python -I sound/soundmap.py "<video>" --show                                       # what a map holds
```

It finds the record whose render has the video's exact picture, then the Real SFX run made from that render whose finished file has the video's exact sound (or none, when the video kept the render's own sound). The song's name comes from `rec.song(path, title=...)`, or from `music.json` / `tracks.csv` in the music library (`../setup/SOUND-LIBRARY.md`), or the tidied file name.

**Without a record** (`--work FOLDER`): it looks for the Real SFX run in that folder (or one level down) whose finished file has exactly the same sound as the video. If the run was mixed from separate `voice.wav`, `nat.wav` and `music.wav`, those are the rows; if `nat_n.wav` (voice and footage sound) and `mix_raw.wav` (that plus music) sit beside the render without effects, the music is the second minus the first; otherwise the render without effects is one row. The effects row is always the run's `*_sfx_ducked.wav` and its `*_resolved_cues.json`.

**By hand**, when a builder keeps its tracks under other names: `--cues RUN_resolved_cues.json` plus any of `--voice`, `--nat`, `--voice-nat`, `--music` (with `--music-minus` to take a file away from it), `--mix` (everything except the effects; name it with `--mix-name`) and `--sfx-track`. `--music-title` names the song. `--dry-run` checks without writing, `--replace` makes a map again.

**The checks.** It refuses, and writes nothing, when the files don't belong to the video: every file must be the video's length (within 0.15 s), together they must account for at least 97% of the video's sound, and in no quarter second may the files and the video differ (an effect added or taken out shows up here). Each row is drawn at its level in the finished mix, on one scale for the whole video, so a quiet track looks quiet next to a loud one. It never changes a video, a notes file or a work folder, and it refuses videos in a `Raw/` folder.

**When the video moves** (for example to `Finished/` when you approve it), move its `.sound.json` with it. A map whose video was re-rendered under the same name isn't shown (the page says so); make it again with `--replace`.

## Adding sounds

- **A pack you buy or download:** `cd ~/.claude/skills/real-sfx && python3 scripts/setup.py add-library NAME "PATH" --tier main --index`.
- **One sound from Openverse:** search with `license=cc0`, download into the right folder of your starter library, add a row to its `catalog.csv` (file, type) and its license list, then `python3 scripts/build_index.py`. Claude shows you each sound's source and license before downloading.
- **Sounds you dislike:** `python3 scripts/taste.py ban ID` (IDs are in the cue report). Real SFX won't pick them again.

## What to say

- "show the sound tracks for <video>": makes the video's sound map.
- "no effects" / "quieter effects" / "louder effects"
- "cut the sound effect at 0:12" (or leave a note on it in Video Review)
