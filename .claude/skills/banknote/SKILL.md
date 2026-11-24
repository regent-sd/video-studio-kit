---
name: banknote
description: "Effect: Your face engraved into an ornate banknote that slides in with a 3D tilt. Put it on a video: /banknote <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /banknote

Your face engraved into an ornate banknote that slides in with a 3D tilt.
- Kind: you, restyled. Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/banknote.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only banknote`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" banknote@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" banknote@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `denomination` | none | what the corners say, e.g. "100" (must be a real amount); default: your key word |
| `title` | none | the big line at the top; default your key word |
| `motto` | none | the line under the portrait; default the sentence you say in the window |
| `paper` | #DDE9D8 | note colour (pale green) |
| `ink` | #173F30 | engraving ink (deep green) |
| `seal` | none | seal colour; default a gold made from the skin's accent |
| `face` | 0.36 | face height as a share of the oval's height |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
