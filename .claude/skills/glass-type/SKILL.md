---
name: glass-type
description: "Effect: Big 3D glass letters of your word stand behind your head and refract the room. Put it on a video: /glass-type <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /glass-type

Big 3D glass letters of your word stand behind your head and refract the room.
- Kind: behind you (uses the cutout). Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/glass_type.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only glass-type`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" glass-type@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" glass-type@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the word; default your key word in the window |
| `font` | sf | sf (SF Pro Black, condensed) / rounded (SF Rounded) / didot |
| `case` | upper | upper / lower / as-said |
| `frost` | 0.35 | 0 = clear acrylic, 1 = fully frosted |
| `tint` | none | glass tint colour; default a cool clear white |
| `dim` | 0.18 | how much the room darkens so the glass reads (0-1) |
| `y` | none | centre of the letters (px); default so your head covers their lower third |
| `lens` | 1.7 | how much the glass shrinks the room seen through it (1 = a flat pane) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
