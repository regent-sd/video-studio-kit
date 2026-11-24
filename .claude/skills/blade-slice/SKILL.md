---
name: blade-slice
description: "Effect: A blade flash slices the frame diagonally; the pieces slide apart, hold, then snap back with a shake. Put it on a video: /blade-slice <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /blade-slice

A blade flash slices the frame diagonally; the pieces slide apart, hold, then snap back with a shake.
- Kind: a camera or body trick. Default length 1.8 s.
- Works as a **transition**: put its window across a cut in an edit, and the cut lands at its peak (about 80% of the way in).
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/blade_slice.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only blade-slice`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" blade-slice@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" blade-slice@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `angle` | -24 | the cut's angle from level (degrees; negative rises to the right) |
| `at` | 0.95 | where it crosses: face-heights below the middle of your face (0 = through the eyes) |
| `pieces` | 2 | 2, or 3 (two parallel cuts) |
| `gap` | 64 | how far the pieces open (px) |
| `slide` | 120 | how far they slide along the cut (px) |
| `tilt` | 1.4 | how much each piece turns (degrees) |
| `color` | none | blade glow colour; default the skin's accent |
| `shake` | 14 | snap-back shake (px) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
