---
name: apple-toggles
description: "Effect: iPhone settings switches under your face that flip on as you say each word. Put it on a video: /apple-toggles <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /apple-toggles

iPhone settings switches under your face that flip on as you say each word.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/apple_toggles.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only apple-toggles`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" apple-toggles@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" apple-toggles@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `rows` | none | [{"label": "Sleep more", "on": "sleep"}, ...]  "on": a word you say, or seconds into the video. Default: the first three key words you say in the window, each flipping on as you say it. |
| `icons` | ["#FF9F0A", "#BF5AF2", "#FF453A", "#3... |  |
| `style` | glass | glass (frosted, light) / dark (iOS dark mode list) |
| `y` | none | top of the card (px); default just under your chin |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
