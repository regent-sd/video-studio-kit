---
name: clone-row
description: "Effect: Copies of you slide out from behind you and recede into the distance on both sides. Put it on a video: /clone-row <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /clone-row

Copies of you slide out from behind you and recede into the distance on both sides.
- Kind: a camera or body trick. Default length 3.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/clone_row.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only clone-row`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" clone-row@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" clone-row@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `copies` | 3 | copies on each side (1-4) |
| `sides` | both | both / left / right |
| `delay` | 4 | frames between one copy and the next (each copy moves a moment after the one in front) |
| `spacing` | 0.21 | gap from you to the first copy, as a share of the frame width |
| `depth` | 0.36 | how quickly they shrink into the distance |
| `fade` | 0.2 | how much darker each copy gets |
| `rise` | 0.0 | lift each copy this share of your face height (0 = eyes on one line, like a real row) |
| `dim_room` | 0.18 | how much the room darkens while the clones are out |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
