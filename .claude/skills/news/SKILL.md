---
name: news
description: "Effect: A newspaper / blog / magazine front page: your words as the headline, you as the photo, your key word highlighted. Put it on a video: /news <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /news

A newspaper / blog / magazine front page: your words as the headline, you as the photo, your key word highlighted.
- Kind: on top of you. Default length 4.5 s.
- Quiet enough for a restrained brand.
- Code: `effects/catalog/news.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only news`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" news@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" news@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `style` | newspaper | newspaper / blog / magazine |
| `masthead` | none | the paper's (or magazine's) name; default none (the newspaper shows the date there instead) |
| `date` | none | the date line; default today's date; "" for none |
| `headline` | none | default: the sentence you say in the window (your own words) |
| `highlight` | none | the word the marker sweeps over; default your key word in the headline |
| `path` | none | blog only: the path line; default ~/<date>/<key word> |
| `color` | none | marker colour; default the skin's accent (yellow) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
