---
name: headline-wall
description: "Effect: Your lines pop up around your head as a post, a search, a sticky note, a clipping, a chat bubble and a headline. Put it on a video: /headline-wall <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /headline-wall

Your lines pop up around your head as a post, a search, a sticky note, a clipping, a chat bubble and a headline.
- Kind: behind you (uses the cutout). Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/headline_wall.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only headline-wall`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" headline-wall@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" headline-wall@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `lines` | none | the snippets, in the order of styles: a list of texts; default lines and phrases you say |
| `styles` | ["clipping", "post", "search", "stick... | which snippets (post / search / sticky / clipping / chat / headline), in pop order |
| `handle` | you | the name on the post card; "" for a blank name bar |
| `dim` | 0.35 | how much the room darkens behind the snippets (0-1) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
