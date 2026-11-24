---
name: live-cursor
description: "Effect: Design-app selection box with its real pixel size, and a named cursor that drags it into place. Put it on a video: /live-cursor <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /live-cursor

Design-app selection box with its real pixel size, and a named cursor that drags it into place.
- Kind: on top of you. Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/live_cursor.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only live-cursor`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" live-cursor@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" live-cursor@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `name` | Editor | the collaborator's name on the cursor tag |
| `color` | none | cursor colour; default the skin's accent (yellow on the Dark skin) |
| `box_color` | none | selection colour; default the skin's blue |
| `label` | none | optional layer name above the box's top-left corner (e.g. a word you say); default none |
| `size` | 1.0 | box size around your head and upper body (1 = head to mid-chest) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
