---
name: setup-studio
description: First-time setup of the video studio kit on a new Mac — install the tools, write studio.json, choose the house rules, set up a brand, a sound library, the voice clone and the demo. Use when the person says "set up my studio", "install the studio", "get me started", "run the setup", or when setup/doctor.py shows things missing.
---

# Set up the studio

You're setting up this kit for its new owner. Work through it in order, one part at a time, and tell them what's next before each part. It takes an hour or two, mostly downloads. They can stop and pick up later: `setup/doctor.py` always shows where things stand.

**Ask before every download or install**: say what it is, where it comes from and roughly how big. Some steps the person must do themselves (anything that asks for their Mac password, `claude mcp add`, opening an unnotarized app, typing `/plugin`); give them the exact command and wait for "done".

## 1. Where things stand

Run `python3 setup/doctor.py` (any Python works for this). Summarise it in a few lines: what's ready, what's missing. Check the kit folder isn't inside iCloud-synced Documents or Desktop; if it is, suggest moving it to `~/Developer` first.

## 2. Install what's missing

Follow `setup/INSTALL.md` in order, skipping what's ready. After the plugins step, remind them to restart Claude Code, then continue (they can say "continue the setup").

## 3. Settings (`studio.json`)

Ask, then copy `studio.example.json` to `studio.json` and fill in:
- Their first name (`owner`), or leave it empty.
- Where their videos should live (`content_root`). Suggest `~/Movies/Video Studio`. A Google Drive or Dropbox folder works too; iCloud-synced Documents doesn't (big files get evicted mid-build).
- Sound and music library folders (defaults are fine).
- Asset Library: do they have a folder of photos, logos and print pieces they'd like searchable? If yes, add it to `asset_roots` (set up later with `assets/README.md`).

Make the content folder with `Footage Log/` and `_To Delete/` inside it.

## 4. House rules

Explain: these are the standing rules Claude follows on every video. Show the headings and rules from `rules/house-rules.starter.md` (short form, not the whole file), then ask:

- **Adopt them all** → copy `house-rules.starter.md` to `rules/house-rules.md`.
- **Go through them one by one** → for each section, ask keep / change / drop per rule; write the result to `rules/house-rules.md`.
- **Start clean** → copy `house-rules.blank.md` to `rules/house-rules.md`.

Also ask whether to keep the *(starter)* lessons in `guides/storytelling.md` or clear them to grow from their own notes only.

## 5. Brand

Run the brand interview (`setup/BRAND-SETUP.md`, or the `set-up-brand` skill). If they'd rather do it later, the example brand works for everything meanwhile.

## 6. Sound library

`setup/SOUND-LIBRARY.md`: build the starter CC0 library (show the list and licenses before downloading), then point Real SFX at it.

## 7. Voice clone (optional now)

`setup/VOICE-STUDIO.md`. They make the clone in the VoiceStudio app themselves; you install the engine and put the profile id in `studio.json`. If they don't want voiceovers yet, skip it.

## 8. Try it: the demo

`demo/README.md`: offer to download the free stock demo clips (say the total size and that each site's license applies), make the demo narration, and render the style samples and effect previews. Then open the Studio page (`.claude/launch.json` → `video-review`, then `/studio`) and show them where the samples are.

## 9. Wrap up

Run `setup/doctor.py` again and list anything still missing with its fix. Then tell them the three phrases to start with: **"log new footage"**, **"start a new edit"** (or the Studio page's Start a new edit), and **"open the studio"**. `guides/what-to-say.md` has the rest.
