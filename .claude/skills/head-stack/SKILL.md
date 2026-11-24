---
name: head-stack
description: "Effect: Word stickers drop onto your head as you say them and stack into a wobbly tower. Put it on a video: /head-stack <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /head-stack

Word stickers drop onto your head as you say them and stack into a wobbly tower.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/head_stack.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only head-stack`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" head-stack@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" head-stack@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `words` | none | ["faster", ...] or [{"text": "...", "on": "word you say" / seconds}]; default your strongest words |
| `max_tags` | 4 | most stickers in the tower (they get smaller when there are more) |
| `case` | upper | upper / lower / as-said |
| `flyby` | true | fast blurred stickers whooshing past behind you (your other words from the video) |
| `colors` | none | list of [background, text] pairs; default the skin's white, accent, dark and blue |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
