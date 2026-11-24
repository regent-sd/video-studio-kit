---
name: cover-story
description: "Effect: A magazine cover: a huge serif masthead behind your head, cover lines of your words, today's date. Put it on a video: /cover-story <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /cover-story

A magazine cover: a huge serif masthead behind your head, cover lines of your words, today's date.
- Kind: behind you (uses the cutout). Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/cover_story.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only cover-story`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" cover-story@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" cover-story@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `masthead` | none | the big word across the top; default your key word in the window, in capitals |
| `lines` | none | cover lines: a list of texts (or {"kicker": "...", "text": "..."}); default short phrases you say |
| `date` | none | the date line; default today's date; "" for none |
| `color` | none | masthead colour; default white |
| `accent` | none | colour of the short rules, the highlighted word in each line and any kickers; default the skin's accent |
| `grade` | 0.6 | how strong the editorial grade is (contrast, warmth, darker top), 0-1 |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
