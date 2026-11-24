---
name: layer-explode
description: "Effect: The shot splits into 3D layers (room, you, a word) that spread apart and turn, then fly back together. Put it on a video: /layer-explode <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /layer-explode

The shot splits into 3D layers (room, you, a word) that spread apart and turn, then fly back together.
- Kind: a camera or body trick. Default length 3.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/layer_explode.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only layer-explode`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" layer-explode@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" layer-explode@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the word on the front layer; default the first key word you say in the window |
| `turn` | 38 | how far the stack turns sideways (degrees) |
| `tilt` | 16 | how far it tips (degrees; we look down on it a little) |
| `spread` | 700 | gap between layers at full size (px) |
| `size` | 0.5 | how big the stack is while apart (share of the frame) |
| `color` | none | word colour; default the skin's accent |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
