---
name: code-body
description: "Effect: You, rebuilt from monospaced characters of your own words, with code rain behind. Put it on a video: /code-body <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /code-body

You, rebuilt from monospaced characters of your own words, with code rain behind.
- Kind: you, restyled. Default length 3 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/code_body.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only code-body`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" code-body@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" code-body@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `text` | none | the characters you're made of; default the words you say in the window (repeated) |
| `cell` | 20 | character cell height in px (width is 0.6 of it); smaller = more detail |
| `color` | #3CFF8F | code colour; the brightest parts go toward white |
| `rain` | 0.6 | background code rain strength (0 = off) |
| `glow` | 0.45 | bloom on the characters |
| `transition` | scan | scan (a scanline wipes down) / dissolve (characters flip in at random) |
| `crawl` | 4.0 | characters per second the text crawls along each row (0 = still) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
