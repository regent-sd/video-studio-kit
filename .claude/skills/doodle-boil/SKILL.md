---
name: doodle-boil
description: "Effect: A boiling hand-drawn chalk outline around you, with crayon doodles and your word around your head. Put it on a video: /doodle-boil <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /doodle-boil

A boiling hand-drawn chalk outline around you, with crayon doodles and your word around your head.
- Kind: behind you (uses the cutout). Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/doodle_boil.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only doodle-boil`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" doodle-boil@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" doodle-boil@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `color` | none | outline colour; default white |
| `accent` | none | doodle colour; default the skin's accent (yellow) |
| `offset` | 22 | how far outside your edge the outline runs (px) |
| `width` | 7 | line thickness (px) |
| `stickers` | ["heart", "star", "sparkle", "crown",... | doodles round your head, in pop order (heart / star / sparkle / squiggle / crown / arrow) |
| `word` | none | a hand-written word by your head; default your key word; "" for none |
| `font` | hand | hand (Bradley Hand) / chalk (Chalkduster) |
| `boil` | 3 | frames between redraws (3 = the classic 10-a-second boil) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
