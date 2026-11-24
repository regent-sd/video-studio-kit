# Video Studio

A video-editing studio run by Claude Code. The owner films; Claude logs the footage, plans and builds edits in named styles, adds effects and sound, and the owner reviews each cut on a local notes page and approves it. Everything here is the instructions, styles, tools and pages. The videos themselves live in the **content folder** that `studio.json` names.

**First time?** If `studio.json` or `rules/house-rules.md` is missing, the studio isn't set up yet: offer to run the setup (`.claude/skills/setup-studio`, "set up my studio").

**Run every Python tool with `.venv/bin/python`** from the kit root (setup makes that environment).

## Read before any edit

1. `rules/house-rules.md`: the owner's standing rules. They come before any style or brand rule.
2. `guides/storytelling.md`: how the owner likes a story told, learned from their notes.
3. The brand's folder, `brands/<brand>/` (`brand.json`, `BRAND.md`, `VOICE.md`). The brand is the one the video or card names, else `default_brand` in `studio.json`.
4. `STYLES.md` and the style's own README.

## Where things are

| Path | What it is |
|---|---|
| `studio.json` | The owner's settings: content folder, brand, sound and music libraries, asset folders, voice clone. Not in git. `studio.example.json` explains each key. |
| `lib/studio_config.py` | How every tool reads those settings and the brands. Nothing personal is ever written into code. |
| `rules/` | The house rules (`house-rules.md`), plus the starter and blank sets setup chose from |
| `brands/` | One folder per brand: colours, fonts, logo, keep-out list, people rules, voice |
| `STYLES.md`, `styles/` | The named styles (Fast Cut with Dark and Brand skins, Talking Head Classic, Hands-On Classic) and their builders |
| `effects/`, `.claude/skills/<effect>/` | 40+ named visual effects, each with a slash command; `/effects` lists them |
| `sound/` | The sound-effects pass every video gets, and sound maps |
| `library/` | The Footage Log (a card and transcript for every raw clip), the video tracker, build records and the finishing step |
| `review/` | Video Review (notes at exact moments), the Studio page (the front door) and the Footage Log pages |
| `assets/` | The Asset Library: a searchable, tagged catalog of the owner's photos, logos and print pieces |
| `walkthrough/` | Narrated product walkthrough videos: script, voiceover, scripted screen recording, film; plus a Remotion product-reel template |
| `demo/` | Free stock demo footage (downloaded on this Mac) and the sample renders |
| `guides/` | `storytelling.md`, `after-approval.md`, `what-to-say.md` (every phrase), `glossary-words.md` |
| `cards/`, `classroom/`, `ideas/` | Project cards from the Studio page; reels saved for their editing; reels saved for what they say |
| `setup/` | Install guide, `doctor.py`, VoiceStudio, brand and sound-library guides |
| `scripts/leak_check.py` | Stops private words, paths and media from going into git |

## Content (the video files)

```
<content_root>/
  <YYYY-MM-DD Title>/          one folder per shoot, named by the first day filmed
    Raw/<camera>/               camera originals, never edited (Camera, POV, Phone, Screen, Photos, or any name)
    Finished/Instagram Reels/   final exports with cover, captions and .srt
    Finished/YouTube/
    Style Tests/                new looks until the owner approves them
    Older Versions/             exports a newer version replaced
  Footage Log/                  clip index, video tracker and their CSVs
  _To Delete/                   broken or duplicate files for the owner to clear
```

- When several projects are filmed on one day, each gets its own dated folder.
- Whether a video is posted lives in the video tracker, not in its folder.
- Review notes sit next to each video as `<video file>.notes.json`. Never delete one.

## Styles: ask which one

There's no default style. When the owner asks for a new video or a re-edit without naming a style, ask which one first, with a one-line description of each from `STYLES.md`. When they name one, use it.

**Building one:** follow "How to make one (for Claude)" in `STYLES.md` and the style's README: plan it with the owner, check `--sheet` (one frame per scene) before the full render, run the sound-effects pass, put it in the shoot's `Style Tests/` with `finish.py`, then open it in Video Review. Builders never overwrite a file and keep a build record so the maps and tracker fill themselves. Look at the frames you made (contact sheets, `--sheet` output) before handing anything over.

**Product walkthroughs** (narrated how-to videos of the owner's own app): `walkthrough/README.md`, or `/walkthrough-video`. Record only a local or test copy of the app with fake data.

## Footage Log and video tracker

Every raw clip has a log card (`<clip>.log.json`) and a transcript (`<clip>.words.txt`) next to it. `Footage Log/video-tracker.json` lists every finished video, test and older version with its status (in review, ready to post, scheduled, posted, shelved, superseded), posted date, link and the raw seconds it used. Details: `library/README.md`.

- **"log new footage"**: `.venv/bin/python library/footage.py prep`, write a card for each new clip from its brief and frame sheets (`library/README.md` has the card format), `.venv/bin/python library/footage.py check` and fix what it lists, then `.venv/bin/python library/usage.py && .venv/bin/python library/footage.py index`.
- **After every export**: put the file in its shoot with `.venv/bin/python library/finish.py <file> "<shoot>/<folder>/<name>.mp4"`. It never overwrites, writes the sound and effects maps from the build record, and refreshes the tracker. Say any map it couldn't make in the hand-off.
- **"find footage of …"**: search `Footage Log/footage-log.json`, or point the owner to the Footage tab.
- **"what's posted / still pending"**, **"mark … posted"**: read or edit `Footage Log/video-tracker.json` (only status, posted_on, post_url, title and notes are hand-kept), then `footage.py index`.

## Video Review and the Studio page

- **"open the studio"** / **"open video review"**: `preview_start` with name `video-review` (`.claude/launch.json`), then `/studio` for the front door.
- **"apply my notes on <video>"**: read `<video>.notes.json`, fix only the open notes, export a new version (v2, v3…, never overwrite the reviewed file), then mark each note done with a one-line reply and the new file. Steps: `review/README.md`, "For Claude".
- **"start the card <name>"**: read the card in `cards/`, the house rules, `guides/storytelling.md`, the brand, the style (if the card says "Ask me", ask which style first) and any classroom cards it names. Propose a plan: the story in order, the footage with times, each effect with its moment and why, any text Claude would write (flagged). Build only after the owner says go. Set the card to "in progress", and "in review" once it's in Video Review.
- **"add this to the classroom: <link>"** (a reel saved for its editing) or **"add this to ideas: <link>"** (saved for what it says). If they don't say which, ask. Formats: `classroom/README.md`, `ideas/README.md`. Write only what the reel shows and what the owner says.
- **"add to the guide: <rule>"**: add it to `guides/storytelling.md` under the right heading, with the date. Never add a rule the owner didn't give.
- **"add a house rule: …"**: add it to `rules/house-rules.md` under the right heading, with the date.
- **"what needs me?"**: cards not yet approved, videos with open notes, videos in review, videos ready to post.
- **When the owner approves a video**: do the routine in `guides/after-approval.md`.

## Sound, effects and voice

- Every new video and re-edit gets a **sound-effects pass** without being asked (`sound/README.md`, using the Real SFX skill and Earshot). List in the hand-off which effects went in so the owner can cut any.
- **Visual effects** go where they land on something said, proposed in the plan with their moment. `.claude/skills/effects/SKILL.md` says when to use which.
- **Voiceovers** use the owner's VoiceStudio clone (`setup/VOICE-STUDIO.md`) and only scripts the owner approved. Claude can't hear: transcribe every take to check the words, and the owner listens before it's used.
- Claude can't hear, so judge sound with **Earshot** (the `earshot` skill), never by guessing.

## Asset Library

If `asset_roots` is set, every file in those folders is in the catalog with a description, tags and flags (`assets/README.md`). Search it first when picking photos or logos. **Read a file's flags before using it publicly** (people visible, children, old logo, prices, dated info, sensitive). People are named only when a folder or file name gives the name, never from a face. Moving or renaming anything goes through `assets/moves.py` so it can be undone; nothing is deleted.

## Sharing the kit

Before any commit, `scripts/leak_check.py` runs (a git hook) and blocks private words (from `~/.config/video-studio-kit/leak-terms.txt`), home-folder paths, emails and media. Never commit `studio.json`, footage, voice files or a brand the owner hasn't chosen to share.
