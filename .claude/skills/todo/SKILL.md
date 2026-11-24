---
name: todo
description: "Effect: A checklist card under your chin that ticks off each item as you say it. Put it on a video: /todo <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /todo

A checklist card under your chin that ticks off each item as you say it.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/todo.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only todo`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" todo@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" todo@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `title` | none | header text, e.g. "Editing your clip"; None: no header (a progress line shows instead) |
| `items` | none | [{"label": "Cut the intro", "tag": "every frame", "on": "intro"}, ...] on: a word you say, or seconds into the video. tag: small green text on the right (optional). Default: one item per key word you say in the window (the word, capitalised), ticking as you say it. |
| `tags` | time | tag for default items: "time" (when the word is said, e.g. 0:05.6) / None |
| `max_items` | 6 | most default items (picked evenly across the window) |
| `rows` | 4 | most rows visible at once; longer lists scroll so the active row stays in view |
| `counter` | true | "2 of 5" at the top right of the header (needs a title) |
| `y` | none | top of the card (px); default just under your chin, or above your head if there's more room |
| `style` | card | card (wide, under your chin) / compact (a small dark card at the top left: tiny caps header, "1 of 3", a thin yellow progress line, yellow checks that fill as you say each item) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
