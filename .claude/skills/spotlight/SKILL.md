---
name: spotlight
description: "Effect: Room goes dark, you stay lit, a glowing word sits behind your head. Put it on a video: /spotlight <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /spotlight

Room goes dark, you stay lit, a glowing word sits behind your head.
- Kind: behind you (uses the cutout). Default length 3.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/spotlight.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only spotlight`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" spotlight@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" spotlight@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the word behind you; default: the first key word you say in the window |
| `color` | none | glow colour; default the skin's accent (yellow on the Dark skin) |
| `font` | didot | didot / bodoni / newyork / sf / skin (the skin's title font: a brand's own, on the Brand skin) |
| `darkness` | 0.78 | how dark the room gets (0-1) |
| `rim` | 0.35 | coloured light on your outline (0 = off) |
| `y` | none | centre of the word (px); default just above your eyes so your head covers its lower half |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
