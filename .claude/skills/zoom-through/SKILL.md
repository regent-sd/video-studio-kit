---
name: zoom-through
description: "Effect: Fast zoom-through whoosh: accelerating push into your face with radial blur and a flash, then back out. Put it on a video: /zoom-through <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /zoom-through

Fast zoom-through whoosh: accelerating push into your face with radial blur and a flash, then back out.
- Kind: a camera or body trick. Default length 1.2 s.
- Works as a **transition**: put its window across a cut in an edit, and the cut lands at its peak (about 50% of the way in).
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/zoom_through.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only zoom-through`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" zoom-through@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" zoom-through@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `peak` | 0.5 | when it's closest: a share of the window (0-1), or seconds into it (over 1). Put it on the cut. |
| `amount` | 5.0 | how close it gets at the peak (5 = five times closer) |
| `blur` | 1.0 | radial motion blur (0 = none, 1 = like a real fast zoom, 2 = smeared) |
| `flash` | 0.8 | brightness flash at the peak (0 = none) |
| `x` | none | the point it dives into (px, or a share of the width); default your face |
| `y` | none | (px, or a share of the height) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
