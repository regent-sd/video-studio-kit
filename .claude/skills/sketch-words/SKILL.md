---
name: sketch-words
description: "Effect: Hand-written marker words and doodles appear on the room as you say them. Put it on a video: /sketch-words <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /sketch-words

Hand-written marker words and doodles appear on the room as you say them.
- Kind: behind you (uses the cutout). Default length 4 s.
- Quiet enough for a restrained brand.
- Code: `effects/catalog/sketch_words.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only sketch-words`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" sketch-words@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" sketch-words@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `words` | none | ["better", ...] or [{"text": "...", "on": "word you say" / seconds}]; default your strongest words in the window |
| `max_words` | 3 | how many words (default picks the longest ones, spread out in time) |
| `font` | hand | hand (Bradley Hand) / chalk (Chalkduster) |
| `color` | none | word colour; default white |
| `doodle` | none | doodle colour; default the skin's accent |
| `doodles` | ["underline", "arrow", "circle"] | per spot (above your head, roomier side, other side): underline / arrow / circle / none |
| `layer` | behind | behind (written on the room, you in front) / front |
| `case` | lower | lower / upper / as-said |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
