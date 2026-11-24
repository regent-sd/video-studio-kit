---
name: comment-drop
description: "Effect: A comment is typed and posted, comment cards drop in from the top, and the word lands huge behind your head. Put it on a video: /comment-drop <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /comment-drop

A comment is typed and posted, comment cards drop in from the top, and the word lands huge behind your head.
- Kind: on top of you. Default length 5 s.
- Not for a brand set to restrained (`"effects": {"restrained": true}` in its brand.json) unless you ask for it.
- Code: `effects/catalog/comment_drop.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only comment-drop`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" comment-drop@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" comment-drop@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
| `comments` | none | [{"user": "you", "text": "better"}, {"user": "...", "text": "...", "likes": 3}, ...] the first is the one typed and posted; "you" gets your face as the avatar. likes: shown under the heart only if given. Default: one comment by "you" with a key word you say. |
| `big_word` | none | the huge word behind your head; default the typed word ("" for none) |
| `style` | light | light (white cards) / dark |
| `placeholder` | Add a comment… |  |
| `max_cards` | 3 | most cards on screen; older ones slide away |

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
