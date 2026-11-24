---
name: dolly-zoom
description: "Effect: Vertigo shot: you stay put while the room zooms in or out behind you, then eases back. Put it on a video: /dolly-zoom <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /dolly-zoom

Vertigo shot: you stay put while the room zooms in or out behind you, then eases back.
- Kind: a camera or body trick. Default length 2.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/dolly_zoom.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only dolly-zoom`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" dolly-zoom@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" dolly-zoom@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `direction` | in | in: the room rushes toward the camera (grows) / out: the room falls away (shrinks) |
| `amount` | 0.32 | how far the room zooms at the peak (0.32 = 32 % bigger, or 1/1.32 smaller for "out") |
| `blur` | 1.0 | radial motion blur on the room while it moves (0 = off) |
| `hold` | 0.16 | share of the window it holds at the peak before easing back |
| `darken` | 0.22 | extra vignette on the room at the peak (0 = off) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
