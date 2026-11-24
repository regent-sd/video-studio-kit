# Classroom

One short card per reel you saved for its **editing**: a look, a cut, an effect, a sound. Each says what the reel does, why it works, what to take from it, what to leave, and what it led to here. The Classroom tab on the Studio page (`/studio/classroom`) lists them with tag filters. Claude reads the ones a project card names before planning an edit, to pitch ideas that fit your script, not to copy them.

This shelf starts empty. Add a reel with **"add this to the classroom: <link>"**.

A reel saved for **what it says** (a strategy, a shooting method, a way of working) is not an editing reference. It goes in `ideas/` instead (`ideas/README.md`). If you send a reel and don't say which, Claude asks: saved for its editing, or for what it says?

## "add this to the classroom: <link>" (for Claude)

1. Open the link (the browser pane, or Chrome if the site needs a sign-in) and read the caption, the slides and the on-screen text. Step through the frames. Claude can't hear the audio, so say so if the words only come from captions. To study it frame by frame, the owner can save it with `yt-dlp` (optional, `setup/INSTALL.md`); keep the file out of the kit.
2. Write `classroom/<creator>-<topic>.md` in the format below (lowercase, hyphens). Fill in only what you saw or what the owner said. Where nothing is known, write "Not written down" or "Nothing recorded".
3. "Why it works" is in the owner's words when they gave any. Your own read is fine, but say it's yours.
4. Reuse tags that are already there (they're the filters on the page). Starter tags: `effects`, `talking-head`, `cutout`, `hook`, `pacing`, `layout`, `captions`, `ending`, `pov`, `product`, `sound`, `tools`, `review`, `workflow`.
5. "What it led to here" starts as "Nothing yet." When something is built from it, add it there. Put effect names in backticks (`` `spotlight` ``) and the Glossary links each effect back to this card.
6. Say it's in the Classroom, in a line.

These cards are your notes on someone else's work: describe what the reel does in your own words, don't copy its captions or script, and keep the link so it's clear whose it is.

## Format

```
# <Creator>: <what the reel is>

- **Creator:** <name or handle>
- **Link:** <the link, or "not recorded">
- **Added:** <YYYY-MM-DD>
- **Tags:** <tag>, <tag>

## What it does
## Why it works
## What we take
## What we leave
## What it led to here
```

The page reads the four fields at the top (`Creator`, `Link`, `Added`, `Tags`) and every `##` section. A file whose name starts with `_` is skipped.
