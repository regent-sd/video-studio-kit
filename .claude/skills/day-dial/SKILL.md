---
name: day-dial
description: "Effect: A huge clock dial behind your head: hour numerals, your word around the rim, a sweeping hand. Put it on a video: /day-dial <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /day-dial

A huge clock dial behind your head: hour numerals, your word around the rim, a sweeping hand.
- Kind: behind you (uses the cutout). Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/day_dial.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only day-dial`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" day-dial@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" day-dial@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `label` | none | the word around the rim; default the key word you say in the window |
| `dial` | #F2EBDD | dial colour (cream paper) |
| `ink` | none | numerals and ticks; default the skin's ink |
| `hand` | none | the sweep hand's disc colour; default the skin's accent |
| `size` | 0.52 | dial radius as a share of the frame width |
| `turns` | 0.75 | how far the hand sweeps over the effect (1 = once round) |
| `numerals` | arabic | arabic (1-12) / roman (I-XII) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
