---
name: digital-zoom
description: "Effect: Camcorder digital punch-in to your face in quick steps, with a glitch on each step and a REC viewfinder. Put it on a video: /digital-zoom <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /digital-zoom

Camcorder digital punch-in to your face in quick steps, with a glitch on each step and a REC viewfinder.
- Kind: a camera or body trick. Default length 3.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/digital_zoom.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only digital-zoom`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" digital-zoom@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" digital-zoom@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `steps` | 2 | how many zoom jumps on the way in (1-4) |
| `max` | 2.0 | the zoom it ends on (2.0 = twice as close) |
| `hud` | true | the viewfinder: corner brackets, REC dot with the real time, zoom bar with the real zoom factor |
| `glitch` | 1.0 | strength of the one-frame digital glitch on each jump (0 = none) |
| `color` | none | HUD colour; default white |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
