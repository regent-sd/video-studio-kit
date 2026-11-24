---
name: phone-mockup
description: "Effect: A phone floats beside you; its app sheet checks off your words one by one, then taps Done. Put it on a video: /phone-mockup <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /phone-mockup

A phone floats beside you; its app sheet checks off your words one by one, then taps Done.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/phone_mockup.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only phone-mockup`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" phone-mockup@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" phone-mockup@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `title` | none | the sheet's title; default your first sentence in the window (cut to 12 words, 3 lines) |
| `items` | none | rows: ["Sleep more", ...] or [{"label": "Sleep more", "on": "sleep"}, ...] on: a word you say, or seconds into the video. Default: the key words you say, each checking off as you say it. |
| `max_items` | 4 | most rows (3-4 fit best) |
| `button` | Done | the pill button's label |
| `side` | none | left / right; default the side with more room |
| `footage` | true | the screen shows your footage behind the sheet; False: a plain light screen |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
