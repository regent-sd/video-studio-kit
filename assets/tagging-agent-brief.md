# Brief for a tagging agent

You are tagging one chunk of the owner's Asset Library so they (and Claude) can search it later: "find a photo of
the shop front", "make a post about the spring launch". You look at contact sheets of previews and write a
description and tags for every file in your chunk. You do not touch the owner's files, or any file other than your
own work file.

Work from the kit folder (the one holding `assets/`), use absolute paths for files you open, run Python as
`.venv/bin/python` (or `python3` if there is no `.venv`), and install nothing. Your caller gives you the chunk name.

## Steps

1. Run `.venv/bin/python assets/tags.py paths <CHUNK>`. It prints where everything is: the rulebook, any reference
   sheets, your chunk's folder and `batch.json`, its sheets, the work file you write, and the check command.
2. Read `assets/TAGGING.md` in full. It is the rulebook: the entry format, the fixed word lists, the flags, and the
   **Your business** section (the owner's own subjects and locations, and how their brand looks now and used to look).
3. If `paths` lists reference sheets, open them first (current logos vs. retired ones), so you can tell
   `brand_status: current` from `retired`.
4. Read your chunk's `batch.json`. For each sheet it lists the cells (A1..C3) with `md5`, `paths` (every place this
   file lives: use the folder names, they carry the shoot, year, place, product and people's names), `name`,
   `kind`, `width`, `height`, `taken`, `duration`, `pages`. `no_preview` lists files with no picture: tag those
   from name, path and kind only, modestly.
5. Open each `sheet-NNN.jpg` with the Read tool (they are images: 3x3 grids, the cell label top left, the file name
   under each picture). Video cells show a 2x2 tile of four frames from the clip. PDF and design cells show page one.
6. Write your entries to the work file `paths` printed: one JSON object, key = the cell's `md5` (if `md5` is null,
   the first entry of `ids`), value = `{description, tags, flags, brand_status}` as TAGGING.md shows. Every file in
   the chunk gets an entry.
   Save as you go: after every 3 or 4 sheets, merge the new entries into the file (a tiny Python snippet that loads
   the JSON if it exists, updates it and writes it back). Don't hold the whole chunk in your head and write it at
   the end.
7. Check: `.venv/bin/python assets/tags.py check <CHUNK>`. Fix what it reports and run it again until it says OK.
   Do NOT run `tags.py apply`.

## What good looks like

- The description says what is literally there, in words someone would search for: "Ceramic mug on a linen cloth,
  morning window light, shot from the side." Not "A beautiful cosy moment."
- Look at each cell properly. Don't copy one description across a run of similar pictures without checking the
  angle, crop and what else is in frame. For a run of near-identical frames, give the best one `rating: 3` (or 2)
  and the rest the `near-duplicate` flag.
- Read what is readable: product and item names on labels, dates, prices, signs. Put names in `item`, and set
  `prices-shown` / `dated-info` when they apply. Never invent a name you can't read or get from the path.
- People: never say who someone is from how they look. Names go in `people` only when the folder path or file name
  gives them. Set `people-visible` whenever a recognisable person is in frame, and `customers-visible` and
  `kids-visible` when they apply.
- Location only from the path or something readable in the picture, using the words in **Your business**.
- `brand_status`: `current` if today's look shows (as **Your business** describes it); `retired` if an old logo or
  look shows (also add the `old-logo` flag) or the file sits in an archive of old brand material; `neutral` if no
  branding is visible.
- Anything with private information (a card number, a signed form, an invoice, staff records) gets `sensitive`.
- Leave out any key you can't support. A wrong tag is worse than a missing one.

## Limits

- Write only your own work file. Do not edit, move, rename or delete anything else. Do not run `previews.py`,
  `catalog.py`, `moves.py`, `chunks.py` or `tags.py apply`.
- Do not start other agents.
- If a sheet won't open, try once more, then tag those cells from `batch.json` alone and say so in your report.

## Report back (short)

Four lines at most: how many entries you wrote, that the check is clean (or what is left), and anything the owner
should know (a folder that looks misfiled, private material, files that look broken). No list of what you tagged.
