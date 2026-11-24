---
name: ui-world
description: "Effect: The top of the frame turns into a light app: a prompt box types your words, then sends. Put it on a video: /ui-world <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /ui-world

The top of the frame turns into a light app: a prompt box types your words, then sends.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/ui_world.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only ui-world`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" ui-world@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" ui-world@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `prompt` | none | what gets typed; default the words you say in the window (ums dropped), typed as you say them. A prompt of your own types at your pace where its words match what you say, else evenly. |
| `app` | none | a small app name above the box (never a real brand); None: no wordmark |
| `placeholder` |  | grey hint in the empty box before typing and after sending (e.g. "Ask anything"); default none |
| `lines` | 3 | most lines of text in the box; older lines scroll up |
| `push` | none | how far the footage eases down (px); default just enough to clear your head (70-300) |
| `surface` | none | the UI colour, e.g. "#f9f7f2"; default warm cream (the Brand skin: its background colour) |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
