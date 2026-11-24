---
name: letter-dive
description: "Effect: A giant serif word on paper with the video playing inside the letters; the camera dives into a letter. Put it on a video: /letter-dive <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /letter-dive

A giant serif word on paper with the video playing inside the letters; the camera dives into a letter.
- Kind: a camera or body trick. Default length 3.2 s.
- Works as a **transition**: put its window across a cut in an edit, and the cut lands at its peak (about 50% of the way in).
- Quiet enough for a restrained brand.
- Code: `effects/catalog/letter_dive.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only letter-dive`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" letter-dive@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" letter-dive@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the word; default the key word you say in the window |
| `font` | bodoni | bodoni / didot (both bold) / skin (the skin's title font: a brand's own, on the Brand skin) |
| `paper` | #F3EEE4 | paper colour |
| `mode` | both | both (zoom out of a letter at the start, dive into one at the end) / in / out |
| `caption` | true | your sentence in small italics under the word |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
