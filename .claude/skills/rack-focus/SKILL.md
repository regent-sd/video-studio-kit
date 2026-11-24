---
name: rack-focus
description: "Effect: Focus pull: room blurred behind you, then the focus shifts to the room (you blur), then back. Put it on a video: /rack-focus <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /rack-focus

Focus pull: room blurred behind you, then the focus shifts to the room (you blur), then back.
- Kind: a camera or body trick. Default length 4 s.
- Quiet enough for a restrained brand.
- Code: `effects/catalog/rack_focus.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only rack-focus`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" rack-focus@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" rack-focus@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `room_blur` | 24 | how out of focus the room gets while you're sharp (px, at 1080 wide) |
| `you_blur` | 16 | how out of focus you get while the room is sharp (px) |
| `breathe` | 0.016 | focus breathing: the picture grows this much (1.6 %) as focus goes to the room |
| `pull` | 0.5 | seconds each focus pull takes (shortened on short windows) |
| `bokeh` | 2.0 | how much bright spots bloom into discs when blurred (1 = plain blur) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
