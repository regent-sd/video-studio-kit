---
name: couch-wall
description: "Effect: The room behind you becomes a tilted wall of big rounded video tiles playing other moments of this video. Put it on a video: /couch-wall <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /couch-wall

The room behind you becomes a tilted wall of big rounded video tiles playing other moments of this video.
- Kind: behind you (uses the cutout). Default length 4.5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/couch_wall.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only couch-wall`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" couch-wall@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" couch-wall@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `images` | none | list of image paths for the tiles; default short loops from this video, playing |
| `cols` | 4 | tile columns across the wall (3-6; fewer = bigger tiles) |
| `tilt` | 12 | perspective tilt of the wall in degrees (0 = flat on) |
| `dim` | 0.86 | how dark the wall between the tiles is (0-1) |
| `border` | 0.4 | brightness of the thin tile borders (0 = none) |
| `loop` | 1.4 | seconds in each tile's loop (played forward, then back) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
