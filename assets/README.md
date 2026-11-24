# Asset Library

A searchable catalog of everything in your marketing folders that isn't raw footage: photos, logos, menus and price lists, labels, print pieces, older videos. Every file gets a one-line description, tags, warning flags and a small preview, so you (or Claude) can say **"find a photo of the shop front"** and get the right file in seconds, and know whether it's safe to post.

It works on any folders you name (one or many, on this Mac or in a synced drive such as Google Drive or Dropbox). Nothing in those folders is changed by the catalog: it only reads. Moving and renaming happen only through `moves.py`, which logs every move so it can be put back.

## What's in this folder

| File | What it does |
|---|---|
| `catalog.py` | Walks your folders and builds the catalog (`scan`); searches it (`find`); lists duplicates (`dups`) |
| `previews.py` | Makes a small preview of every file (`run`), and contact sheets for tagging (`sheets`, `reference`) |
| `chunks.py` | Splits the contact sheets into agent-sized chunks, and merges the agents' work back |
| `tags.py` | Checks the agents' tags against `TAGGING.md` and files them (`check`, `apply`, `status`, `sample`) |
| `moves.py` | Moves and renames from a plan: `check`, `apply`, `undo`, `verify`. Nothing is ever deleted |
| `TAGGING.md` | The rulebook: the fixed word lists and flags, plus a **Your business** section you tailor |
| `tagging-agent-brief.md` | What each tagging agent is told to do |
| `render.swift` | The preview renderer (compiled once; Pillow and macOS's `sips` stand in without it) |
| `assetlib.py` | Settings and helpers the others share |
| `browser/` | The search page: `page.html`, `serve.py` (inside Video Review), `build.py` (the shareable Artifact), `slim.py` |

## Set it up for your folders

Add these to `studio.json` at the kit root:

```json
"asset_roots": ["~/Pictures/Brand Photos", "~/Dropbox/Marketing"],
"asset_library_dir": "~/Movies/Video Studio/_Asset Library",
"asset_never_move": ["Marketing/Shared With Printer"],
"asset_exclude": ["Marketing/Old Website Backups"]
```

| Setting | What it is | Default |
|---|---|---|
| `asset_roots` | The folders to catalog. Each root's own folder name starts every path in the catalog, e.g. `Marketing/Logos/badge.png` | none (no Asset Library yet) |
| `asset_library_dir` | Where the catalog, tags, media facts, move log and snapshots live. Put it in a synced drive if others should see the CSV | `~/Movies/Video Studio/_Asset Library` |
| `asset_cache_dir` | Previews, contact sheets and work files. Thousands of small files: keep them out of iCloud and out of a synced drive | `<asset_library_dir>/cache.nosync` |
| `asset_never_move` | Folders or files `moves.py` must never move or rename (shared with someone else, linked from a website). An absolute path, `<root name>/...`, or with one root a path inside it | none |
| `asset_exclude` | Folders left out of the catalog entirely | none |

Always left out: your shoots folder (`content_root`, which the Footage Log covers), the library folder and the cache, and any name starting with a dot.

**Synced drives.** Google Drive, Dropbox and iCloud can keep files "online only". The catalog never downloads anything to list it. To find exact duplicates it hashes every file that is already on this Mac; online-only files are hashed only with `scan --hash-online` (which downloads them; it can take a while and a lot of disk). Without a hash, duplicates are matched by name and size. Previews do download each file they draw, a few at a time, and stop before free space falls under 8 GB (`--floor`).

**iCloud and the cache.** If your Documents or Desktop sync to iCloud with "Optimize Mac Storage" on, iCloud can push previews online in the middle of a run. A folder whose name ends in `.nosync` is skipped by iCloud, which is why the cache defaults to `cache.nosync`. The scan warns if the cache is somewhere iCloud may touch.

**Your words.** Open `TAGGING.md` and fill in **Your business**: your own subjects, your locations, how your brand looks now and how it used to look. Or say **"set up my asset tags"** and Claude asks you and writes it.

## What to say to Claude

| Say | What happens |
|---|---|
| **"find a photo of …"**, "do we have a logo for …", picking pictures for a post | Claude searches the catalog (`catalog.py find`), reads each file's flags, and gives you the best few with their paths. It doesn't dig through folders. |
| **"log new assets"** | The full routine below: scan, previews, contact sheets, tagging agents, apply, refresh the page. |
| **"set up my asset tags"** | Claude asks about your business and fills in **Your business** in `TAGGING.md`. |
| **"open the asset library"** | Video Review's page at http://127.0.0.1:8765/assets (the Assets tile on the Studio page). |
| **"publish the asset library"** | Builds the shareable page and publishes it as a private Artifact (below). |
| **"tidy up the logos folder"**, "move … to …", "clear out the duplicates" | Claude writes a move plan, shows you `moves.py check`'s report, and applies it only after you say yes. |
| **"undo the last move"** | `moves.py undo`, then `moves.py verify`. |

## Find a photo of…

```
.venv/bin/python assets/catalog.py find shop front
.venv/bin/python assets/catalog.py find --type photo --subject product --use ready-to-post --rating 2 --not-flag people-visible,old-logo
.venv/bin/python assets/catalog.py find logo --brand current --type logo
.venv/bin/python assets/catalog.py find spring --campaign "Spring 2026" --json
```

Words must all appear somewhere in the path, description, tags or flags. Filters: `--kind` (photo, graphic, pdf, video, …), `--root`, `--top`, `--ext`, `--type`, `--subject`, `--setting`, `--location`, `--item`, `--people`, `--campaign`, `--use`, `--brand` (brand status), `--year`, `--rating N` (N or better), `--flag a,b` (any of), `--not-flag a,b` (none of), `--locked` / `--unlocked`. One row per unique file, best rated first, with its full path (or its Drive link); `--all-copies` lists every copy, `--to-delete` includes `_To Delete` folders, `--json` gives everything.

**Before a file is used anywhere public, read its flags:**

- `people-visible`, `customers-visible`, `kids-visible`: get that person's OK first (a parent's, for a child; keep children out unless they say yes).
- `old-logo`, or brand status `retired`: an old look, not for new work.
- `prices-shown`, `dated-info`: may be out of date.
- `sensitive`: private paperwork. Never use it; it shouldn't be in a marketing folder at all (the search page shows no preview of it).

The tags are written by agents from small previews. They're right most of the time, not every time: look at the real file before it goes out, and don't lean hard on `rating` or `year`.

People are named only when a folder or file name gives the name. Never from a face.

## Log new assets

Run after files are added to your folders, or the first time. Each step is safe to re-run.

1. `.venv/bin/python assets/catalog.py scan` lists everything and hashes new files.
2. `.venv/bin/python assets/previews.py run` makes previews for anything new (photos first, then PDFs, design files, video, audio).
3. `.venv/bin/python assets/previews.py sheets` makes 3x3 contact sheets of the files **not yet described** (`--all` for every file), batched by folder. It rebuilds the sheets from scratch, so never run it while tagging is under way.
4. If your logo changed over the years, make reference sheets once: `previews.py reference current "<root>/Brand/Logos/Current"` and `previews.py reference retired "<root>/Brand/Logos/Old"`.
5. `.venv/bin/python assets/chunks.py make` splits the batches into chunks of up to 18 sheets (about 150 files), plus one chunk per batch for the files with no preview.
6. **Tagging agents.** Claude starts one subagent per chunk (a smaller model such as Sonnet does this well; up to about 10 at once), each with this prompt:
   > Read `assets/tagging-agent-brief.md` in the kit folder and follow it for chunk `<chunk name>`.

   Each agent writes its own work file and checks itself with `tags.py check <chunk>`. About five minutes per chunk.
7. `.venv/bin/python assets/chunks.py status`, then `chunks.py merge` (only batches whose chunks are all done), then `.venv/bin/python assets/tags.py apply <batch>` for each one. Apply checks again, files the tags and re-scans.
8. Spot-check: `tags.py sample <batch>` makes review sheets (preview plus its tags) in the cache. Fix a wrong entry in the batch's work file and apply again (the newest file wins).
9. Refresh the shareable page if you have one: `browser/build.py`, then republish to the same link.

`tags.py status` shows what's tagged, what's applied, and how often each word is used.

## The search page

One page (`browser/page.html`), two ways to open it:

- **On this Mac:** http://127.0.0.1:8765/assets in Video Review. It reads the live catalog, so it is always current. Each file shows its preview, description, warnings, every copy, and buttons to copy the path or a line for Claude.
- **As an Artifact, to share:** `.venv/bin/python assets/browser/build.py --out <folder>` writes a bundle (`index.html`, `data/assets.json`, `sprites/`) with previews packed 100 to a sheet. To publish it, Claude builds into its session's scratchpad folder and publishes `index.html` with the bundle's files; `_publish.json` lists them, split into rounds when the bundle is bigger than one publish takes (255 files, 64 MB), each later round going to the same link. The bundle has no paths on your Mac and no checksums, but it does show your photos, including people: an Artifact is private until you share it, so share it only with your team. Re-run the build after new previews or tags, then republish to the same link.

The page: search names, folders, descriptions and tags; filters for kind, folder and every tag; toggles to hide people, hide old branding, show only ready-to-post or only files with a preview; duplicates collapsed (and `_To Delete` hidden) unless "Show every copy" is on; a list view with CSV; the view is kept in the link.

For the review page's code: `review/review.py` loads `browser/serve.py` on first use and passes it every request under `/assets` as `handle(h, method, u)`. `serve.summary()` gives counts for a Studio tile, or None before the first scan.

## Moving files

Plans are CSVs you (or Claude) write, kept in `<asset_library_dir>/plans/`:

```
order,from,to,kind,reason,id
1,Marketing/Photos/IMG_1234 copy.jpg,Marketing/_To Delete/Photos/IMG_1234 copy.jpg,file,duplicate: same as Marketing/Photos/IMG_1234.jpg,
2,Marketing/Logos 2019,Marketing/Brand/Logos/Old/2019,folder,layout: old logos together,
```

Paths are catalog paths, exactly as `find` prints them. `kind` is file or folder. `reason` starts with a word and a colon (`duplicate:`, `layout:`, `junk:`, `empty:`). `id` may be empty; if given, the item there must have that id.

```
.venv/bin/python assets/moves.py check <plan.csv>     simulate the whole plan; refuses anything unsafe
.venv/bin/python assets/moves.py apply <plan.csv>     re-scan, re-check, snapshot, then move and log each item at once
.venv/bin/python assets/moves.py verify [batch]       re-scan and compare: same files, same content, locked items untouched
.venv/bin/python assets/moves.py undo [batch]         move a batch back, last move first
.venv/bin/python assets/moves.py log                  list the batches
```

Rules `check` enforces: nothing is ever deleted (unwanted files go to a `_To Delete` folder at the top of their root, for you to empty yourself); a file only goes to `_To Delete` if another copy stays, unless its reason is `junk:` or `empty:`; nothing in `asset_never_move`, `asset_exclude`, your shoots folder or the library is touched; no destination may already exist, and names that differ only by case clash on a Mac; a whole root never moves; a move between roots works only on the same disk. Every move is written to `move-log.csv` the moment it happens, so an interrupted run can still be undone. On Google Drive for desktop, a move in Finder or by these tools is a real Drive move: links and sharing stay.

## Files it writes

In `asset_library_dir`:

| File | What it is |
|---|---|
| `asset-catalog.json` | Every file, folder and problem. Generated: don't edit |
| `asset-catalog.csv` | One row per file, for a spreadsheet |
| `media.json` | Written by `previews.py`: pixel size, length, page count, date taken, preview name |
| `tags/<batch>.json` | Written by `tags.py apply`: description, tags, flags, brand status |
| `move-log.csv`, `snapshots/`, `plans/` | The move log, the catalog as it was before each batch, your plans |
| `README.txt` | A short note for anyone who finds the folder |

In the cache: `thumbs/` (one 640 px JPEG per unique file), `sheets/`, `chunks/`, `tags-work/`, `tags-review/`, `reference/`, `bin/render`, `hashes.json`, `previews.log`, `bundle/`.

## The catalog, field by field

| Field | Meaning |
|---|---|
| `id` | This copy's id: its Google Drive id when the file is in Google Drive for desktop, else one that lasts while the file stays on the same disk (moves and renames keep it) |
| `path` | `<root name>/<path inside the root>` |
| `root`, `top`, `folder` | The root's name; the first folder inside it; the folder the file is in |
| `name`, `ext`, `kind` | File name; extension; kind (below) |
| `bytes`, `modified`, `created` | Size (a package counts its whole contents) and dates |
| `md5` | Content hash; null for packages and online-only files not hashed |
| `dup_group`, `dup_basis` | Duplicates: `md5` (certain), `name+size` (strong), `size` (probable) |
| `link`, `drive_id` | Google Drive link and id, when there is one |
| `locked` | Under `asset_never_move` |
| `package`, `local`, `camera_name` | A macOS package (`.pages`, `.key`, …) counted as one file; downloaded to this Mac; a camera's default name like `IMG_1234` |
| `width`, `height`, `duration`, `pages`, `taken`, `thumb`, `preview_error` | From `media.json` (width and height are points for PDFs) |
| `description`, `tags`, `flags`, `brand_status` | From `tags/*.json` |

`problems` lists what a person should know: `missing-root`, `unreadable`, `link` (a symlink or drive shortcut, not followed), `alias` (a Finder alias), `space-at-end-of-name`, `slash-in-name`, `temp-file`, `copied-drive-id` (a Finder copy kept the original's Drive id; its link is left out), `bad-tags-file`, `bad-media-file`.

**Kinds:** photo (jpg, heic, tif, camera raw), graphic (png, svg, gif, webp), design-source (ai, psd, eps, indd, fig, sketch, …), pdf, video, audio, doc (Office, Pages, Google, txt, csv, …), font, project (Premiere, After Effects, Final Cut XML, …), archive, other.

## The merge contract (for anything that adds fields)

Never edit `asset-catalog.json` or the CSV; the next scan rewrites them. Write your own file and scan:

- **Tags:** `tags/<your-name>.json`, `{ "<md5, or id when there's no md5>": {"description", "tags", "flags", "brand_status"} }`. Any key may be left out. Files are applied oldest first, so a later file wins per key; to clear a value, write `null`, `[]` or `{}`.
- **Media:** `media.json`, `{ "<md5 or id>": {"width", "height", "duration", "taken", "pages", "thumb", "preview_error"} }`.
- Key by content (the md5), never by path: every copy of a file shares its tags, and moves never break them.
- Write atomically (a temp file in the same folder, then rename).
- A tags or media file that isn't a JSON object is skipped and listed in `problems`.
