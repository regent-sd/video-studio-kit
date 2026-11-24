---
name: chart-grow
description: "Effect: A glowing line chart draws itself across the room behind you, the last point lit up. Put it on a video: /chart-grow <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /chart-grow

A glowing line chart draws itself across the room behind you, the last point lit up.
- Kind: behind you (uses the cutout). Default length 4.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/chart_grow.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only chart-grow`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" chart-grow@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" chart-grow@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `values` | none | real numbers to plot, in order, e.g. [231, 226, 222, 219]; scaled to fit. None: a decorative rising curve (decorative, not data): no numbers, no labels. |
| `labels` | none | a short label under each point, e.g. ["Jun", "Jul", "Aug", "Sep"] (only with values) |
| `unit` | none | added after the last value in its callout, e.g. "lb" |
| `callout` | true | the last value in a pill by its point (only with values) |
| `color` | none | line colour; default the skin's accent |
| `dim` | 0.28 | how much the room darkens behind the chart (0-0.6) so the glow reads |
| `grid` | 5 | horizontal grid lines |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
