# Ideas

Reels you saved for **what they say**, not for how they're cut: what to make, how to plan it, how to shoot it, how to work. One short card each. The Ideas tab on the Studio page (`/studio/ideas`) lists them with tag filters.

This shelf starts empty. Add a reel with **"add this to ideas: <link>"**.

There are two shelves for saved reels:

| Shelf | What goes there | Who uses it |
|---|---|---|
| `classroom/` | A reel saved for its **editing**: a look, a cut, an effect, a sound | Claude reads the ones a project card names before planning an edit |
| `ideas/` | A reel saved for its **content**: a strategy, a shooting method, a way of working | You, and whoever plans what to make. Never an editing reference |

**For Claude:** don't read these when planning an edit, don't offer them on a project card, and don't copy how these reels look. They only come up when the owner asks about the idea itself, or when planning what to make.

## "add this to ideas: <link>" (for Claude)

1. Open the link (the browser pane, or Chrome if the site needs a sign-in) and read the caption, the slides and the on-screen text. Step through the frames. Claude can't hear the audio, so say so if the words only come from captions.
2. Write `ideas/<creator>-<topic>.md` in the format below (lowercase, hyphens). Fill in only what you saw or what the owner said. Where nothing is known, write "Not written down" or "Nothing recorded".
3. "Why it works" is in the owner's words when they gave any. Your own read is fine, but say it's yours.
4. Reuse tags that are already there (they're the filters on the page). Starter tags: `hook`, `structure`, `testing`, `planning`, `b-roll`, `shooting`, `organisation`, `workflow`, `tools`.
5. "What it led to here" starts as "Nothing yet." When a plan, a shot list or a tool comes out of it, add it there.
6. Say it's in Ideas, in a line.

If a reel comes without saying which shelf, ask: saved for its editing, or for what it says? One reel can have a card on both shelves if the owner wants both. To move a card between shelves, move the file between `classroom/` and `ideas/`; the page picks it up on the next load.

Describe the idea in your own words, don't copy the reel's script, and keep the link so it's clear whose idea it is.

## Format

```
# <Creator>: <what the reel is about>

- **Creator:** <name or handle>
- **Link:** <the link, or "not recorded">
- **Added:** <YYYY-MM-DD>
- **Tags:** <tag>, <tag>

## What it says
## Why it works
## What we take
## What we leave
## What it led to here
```
