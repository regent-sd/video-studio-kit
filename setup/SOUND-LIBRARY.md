# Your sound library and music

Every video gets a sound-effects pass (`sound/README.md`): a pop when a tag appears, a whoosh into a card, a tick on a counter. Those are **real recordings** picked from your own library, never generated tones. This page builds that library and points the tools at it.

The kit ships no sounds: sound packs have their own licenses, and you choose what you use.

## Where it lives

`studio.json` → `sound_library` (default `~/Music/Sound Effects`). Keep it outside iCloud-synced folders. One folder per kind of sound works well:

```
~/Music/Sound Effects/
  Starter CC0/
    whoosh/  pop/  click/  hit/  riser/  tick/  chime/  paper/  typing/  ...
  <any pack you buy>/
```

## 1. Start with free, no-strings sounds (CC0)

CC0 sounds are free for any use, commercial included, with no credit required. Good sources:

- **Freesound** (https://freesound.org): filter by license **Creative Commons 0**. A free account is needed to download.
- **Openverse** (https://openverse.org/audio, or its API `https://api.openverse.org/v1/audio/?q=whoosh&license=cc0`): search across sources; keep the license line it gives.
- The **uisfx** set bundled with Real SFX: 78 CC0 interface sounds (clicks, toggles, notifications), added with `--uisfx` below.

Ask Claude: *"Build me a starter CC0 sound library: about 100 sounds across whooshes, pops, clicks, hits, risers, ticks, chimes, paper and typing."* Claude searches, uses Earshot to listen to the candidates and keep the clean, real-sounding ones, shows you the list with each sound's source and license **before downloading anything**, and saves a `LICENSES.csv` in the folder.

Paid packs you've bought (Envato, Epidemic, Artlist, Soundsnap…) go in their own folder next to it. Keep the license that came with them.

## 2. Point Real SFX at it

```bash
cd ~/.claude/skills/real-sfx
python3 scripts/setup.py init --library main="$HOME/Music/Sound Effects/Starter CC0" --uisfx --index
python3 scripts/setup.py check
```

Add more libraries later:

```bash
python3 scripts/setup.py add-library mypack "$HOME/Music/Sound Effects/<pack>" --tier main --index
```

Earshot also ships a bank of sounds made in code. They're a fallback for when nothing real fits, and they render with no download: ask *"render the Earshot bank into my sound library as a fallback folder"*.

## 3. Music

- **Every video gets its own track.** Never reuse one across videos; the video tracker remembers which track each video used.
- Real licensed tracks you pick sound better than generated music, which tends to sound generic.
- Put the tracks you've licensed in `studio.json` → `music_library` (default `~/Music/Video Music`), one file per track, with its license next to it. Keep a `tracks.csv` in that folder with the columns `file, title, artist, source, license` (the studio reads the song's name from it for each video's sound map), or a `music.json` that maps each file name to "Title (Artist)".
- Royalty-free sources include Envato, Artlist, Epidemic Sound, Musicbed and the YouTube Audio Library. Read what each license covers: some don't cover ads, or end when your subscription ends.
- Music from Instagram's or TikTok's own library can only be added inside those apps when you post.

## 4. Check

```bash
.venv/bin/python setup/doctor.py
```

"Sound library" and "Real SFX sound library" should both be ready.
