---
name: blow-away
description: "Effect: You crumble into dust and blow away, leaving the empty room, then reassemble. Put it on a video: /blow-away <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /blow-away

You crumble into dust and blow away, leaving the empty room, then reassemble.
- Kind: a camera or body trick. Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/blow_away.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only blow-away`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" blow-away@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" blow-away@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `back` | true | reassemble near the end (False: stay gone to the end of the window, e.g. the last shot of a video) |
| `side` | right | where the crumbling starts: right / left / top |
| `wind` | 1.0 | how hard the dust blows (to the right and up) |
| `grain` | 3 | dust size: one speck per grain x grain px of you (2 = finer and slower, 4 = coarser) |
| `plate` | none | a photo of the empty set (same framing) for a clean room; default: worked out from the video |
| `dim` | 0.35 | how much the worked-out room behind you is darkened (ignored with a real plate photo) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
