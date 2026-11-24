---
name: arch-text
description: "Effect: Your line arches over your head like a rainbow, behind you; rises as your hand goes up, words light as you say them. Put it on a video: /arch-text <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /arch-text

Your line arches over your head like a rainbow, behind you; rises as your hand goes up, words light as you say them.
- Kind: behind you (uses the cutout). Default length 3 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/arch_text.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only arch-text`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" arch-text@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" arch-text@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the line; default the words you say in the window (your own words) |
| `fixes` | {} | {"heard": "meant"}: words the transcript got wrong ("mane" -> "Main") |
| `lines` | none | the arcs, top to bottom, e.g. ["Come along", "to the market", "with me"]; default: split for you |
| `big` | none | which line is set big (index); default the longest |
| `sizes` | none | or a size for every line, as a share of the big size, e.g. [0.55, 1.2, 1.0, 0.55] (0.8 and up are "big") |
| `color` | none | the letters; default the skin's light colour |
| `small_color` | none | the small lines; default the same as color |
| `size` | 1.0 | overall type scale |
| `small_font` | heading | the small lines' font: "heading" or "title" (the skin's fonts) |
| `radius` | 4.0 | inner arc radius, in face heights (bigger = flatter arch) |
| `clear` | 0.12 | gap between the top of your head and the inner arc, in face heights (negative tucks it behind) |
| `spread` | 118 | widest an arc may open, degrees: a line that would open wider is set smaller |
| `width` | 0.92 | widest an arc may be, as a share of the frame width |
| `dim` | 0.34 | opacity of a word before it's said (1 = no lighting) |
| `glow` | 0.45 | brief glow when a word lights (0 = off) |
| `rise` | hand | "hand": land as your raised hand peaks; "word": land on the first word; or [start, land] seconds into the effect |
| `rise_dur` | 0.55 | seconds from start to landing |
| `land_at` | 0.94 | with rise="hand": land when the hand is this close to its highest (0-1) |
| `land_delay` | 0.05 | ... plus this many seconds |
| `rise_from` | 170 | px below its spot it rises from (from behind your head) |
| `overshoot` | 1.6 | how far it overshoots as it lands (0 = none) |
| `stagger` | 0.035 | seconds between lines landing (innermost first) |
| `tilt` | 5.0 | degrees each line swings in from |
| `shadow` | 0.7 | soft shadow under the letters |
| `backdrop` | 0.16 | how much the room darkens just behind the letters, so they read (0 = off) |
| `stroke` | 0.0 | px of extra weight on the letters (thickens a thin display face's hairlines) |
| `hold_out` | 0.0 | seconds at the end to fade out (0 = stays to the last frame, for a hard cut) |
| `case` | upper | upper / as-is |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
