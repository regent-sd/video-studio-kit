---
name: paper-tear
description: "Effect: A paper sheet with your word drops over the frame, then tears open to reveal you. Put it on a video: /paper-tear <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /paper-tear

A paper sheet with your word drops over the frame, then tears open to reveal you.
- Kind: on top of you. Default length 3 s.
- Works as a **transition**: put its window across a cut in an edit, and the cut lands at its peak (about 30% of the way in).
- Quiet enough for a restrained brand.
- Code: `effects/catalog/paper_tear.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only paper-tear`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" paper-tear@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" paper-tear@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the word on the sheet; default the key word you say in the window |
| `line` | true | your sentence in small type under the word |
| `mode` | split | split (rips in two, the halves fall away) / sweep (a torn edge sweeps across) |
| `close` | false | True: the tear closes back up near the end, then the sheet drops away |
| `tear_at` | none | seconds into the effect when it rips; default about 40% in |
| `paper` | #F3F0E9 | sheet colour |
| `ink` | none | word colour; default the skin's ink |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
