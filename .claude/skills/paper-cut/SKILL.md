---
name: paper-cut
description: "Effect: Scrapbook collage: you as a die-cut sticker on torn paper scraps, your word in ransom-note letters, stop-motion. Put it on a video: /paper-cut <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /paper-cut

Scrapbook collage: you as a die-cut sticker on torn paper scraps, your word in ransom-note letters, stop-motion.
- Kind: you, restyled. Default length 4 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/paper_cut.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only paper-cut`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" paper-cut@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" paper-cut@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the ransom-note title; default the key word you say in the window |
| `size` | 0.9 | your size on the page (share of full size; made smaller if your head would hit the title) |
| `border` | 26 | thickness of the white sticker border (px) |
| `page` | #D6BC95 | the page under the scraps (kraft card) |
| `steps` | 3 | frames per stop-motion step (2 = on twos, 3 = on threes) |
| `seed` | 7 | a different number shuffles the scraps, fonts and colours |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
