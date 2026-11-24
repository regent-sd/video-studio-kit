---
name: pull-back
description: "Effect: The camera pulls back: your clip plays in an app window, a 'Working on' card ticks off steps, a render bar fills. Put it on a video: /pull-back <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /pull-back

The camera pulls back: your clip plays in an app window, a 'Working on' card ticks off steps, a render bar fills.
- Kind: a camera or body trick. Default length 6 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/pull_back.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only pull-back`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" pull-back@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" pull-back@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `items` | none | the card's steps: ["Trim the intro", ...] or [{"label": "Trim the intro", "on": "intro"}, ...] on: a word you say, or seconds into the video. Default: the key words you say, each ticking off as you say it. Steps without a time are spread over the window. |
| `max_items` | 4 | most default steps |
| `header` | Working on | the card's header (Claude's wording: flag it before posting) |
| `status` | Rendering | the label on the bar under the window (Claude's wording: flag it); "" for none |
| `title` | none | text in the window's title bar; None: just the three dots |
| `percent` | true | the bar's percentage (it follows the effect's own time, not a real render) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
