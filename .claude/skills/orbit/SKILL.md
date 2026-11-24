---
name: orbit
description: "Effect: A ring of thumbnail cards orbits your head in 3D, behind you at the back, in front at the front. Put it on a video: /orbit <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /orbit

A ring of thumbnail cards orbits your head in 3D, behind you at the back, in front at the front.
- Kind: behind you (uses the cutout). Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/orbit.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only orbit`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" orbit@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" orbit@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `images` | none | list of image paths for the cards; default stills from this video at spread-out times |
| `count` | 10 | how many cards (8-12 looks best) |
| `speed` | 1.0 | turns per 7 seconds; negative spins the other way |
| `size` | 1.0 | card size |
| `ring` | true | draw the faint orbit line |
| `tilt` | 1.0 | how tilted the ring is (1 = the front passes below your chin) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
