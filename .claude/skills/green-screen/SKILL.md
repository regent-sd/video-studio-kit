---
name: green-screen
description: "Effect: Creator green-screen layout: you cut out low in frame over a dark backdrop, a card of other footage above you. Put it on a video: /green-screen <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /green-screen

Creator green-screen layout: you cut out low in frame over a dark backdrop, a card of other footage above you.
- Kind: behind you (uses the cutout). Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/green_screen.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only green-screen`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" green-screen@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" green-screen@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `media` | none | an image or video for the card (a path; a relative one starts in the content folder); default this video |
| `at` | none | seconds into the media (or this video) to show; default the start of this video |
| `live` | true | True: the card plays from `at`; False: it holds a still |
| `layout` | bottom | bottom: you sit low with the card above you / full: the footage fills the frame behind you, you stay as you are |
| `color` | none | backdrop colour; default the skin's dark colours with a soft glow of its accent |
| `size` | 0.7 | your size in the bottom layout (share of full size; made smaller if your head would rise past the middle) |
| `rim` | 0.55 | light on your outline (0 = off) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
