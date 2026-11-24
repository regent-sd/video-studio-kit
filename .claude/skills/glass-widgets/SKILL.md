---
name: glass-widgets
description: "Effect: Frosted-glass widget cards (stat, chart, progress, ring, profile, pill) float around your head. Put it on a video: /glass-widgets <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /glass-widgets

Frosted-glass widget cards (stat, chart, progress, ring, profile, pill) float around your head.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/glass_widgets.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only glass-widgets`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" glass-widgets@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" glass-widgets@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `stat` | none | {"value": "3x", "label": "per week"}: a real number for the big card. Default: no number; the card shows the latest strong word you say. |
| `ring` | none | a real 0-1 value (or "75%") for the ring card, with ring_label. Default: rings that fill with the effect's time |
| `ring_label` | none | small text under a ring value |
| `progress_label` | Rendering | the progress card's label (its % is the effect's own time, not a claim) |
| `name` | none | name on the profile card (the avatar is your face from the video). Default: no name, placeholder lines |
| `editor` | none | "Edited by <editor>" pill. Default: a recording dot and the video's own timecode |
| `cards` | none | which cards, e.g. ["stat", "chart", "progress", "ring", "profile", "pill"]; default all of them |
| `style` | light | light (white frosted glass, dark text) / dark (smoked glass, white text) |
| `follow` | 0.5 | how much the cards follow your head (0 = stay put, 1 = stuck to it) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
