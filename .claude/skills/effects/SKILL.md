---
name: effects
description: The effects library (effects/): 42 named visual effects (spotlight, todo, news, paper-tear, zoom-through, orbit, impact-frame, dolly-zoom, cover-story, green-screen...) that go on any stretch of any video, each with its own slash command. Use when the owner types /effects or one of the effect commands, asks for an effect by what it looks like (a checklist, a newspaper, a glowing word behind me, clones, dust, a keyboard, a zoom transition...), asks to preview the effects on their footage, AND whenever you plan or build a new video edit (Fast Cut, Talking Head Classic, Hands-On Classic) to decide whether an effect fits a moment.
---

# Effects

42 effects, each with its own slash command (`/spotlight`, `/todo`, `/orbit`…, written by
`.venv/bin/python effects/fx.py commands`; `/checklist` is todo in its compact style, `/vertigo` is dolly-zoom).
`/effects` alone: show the list by kind from `effects/README.md` (what each does, when it fits, its length) and offer
previews on their own footage. `.venv/bin/python effects/fx.py list` lists them by kind; each effect's
`.claude/skills/<effect>/SKILL.md` has every setting.

**In review:** none yet. New effects stay on the README's in-review list until the owner approves them for reuse;
don't put an unapproved effect into an edit without saying it's new.

## Previews on their footage
`.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> [--brand <slug>] [--only a,b]`
renders `FX_<effect>.mp4` for each effect, `contact.jpg` and `previews.json` from any folder of clips (it picks a
talking clip for most effects and a B-roll clip for the transitions). Put the output in a shoot's `Style Tests/Effects`.
All 42 take a while: start with `--only` a few, or `--sheet-only`. Read `contact.jpg` before you show it.

## On a video that already exists
1. **Find the video.** Raw clips and finished videos are under the content folder (`studio.json`'s `content_root`).
   A raw clip needs `--from/--to` (and `--grade camera` for main-camera originals, `--grade pov` for glasses or
   head-mounted footage). A finished video already has captions burned in: card effects are fine on it, but effects
   that darken or redraw the frame (spotlight, impact-frame, the restyles) also darken its captions, so for those
   prefer rebuilding the edit with the effect (below).
2. **Pick the moment** from the transcript (`<clip>.words.txt`, or the subject's `words.json` after `fx.py prep`).
   `<when>`: `7.2-10.6`, `7.2`, `finally` (starts on that word), `finally+4`.
3. **Settings.** Text defaults to the speaker's own words. Any label, title, name or comment you write goes in `--set`,
   and you flag it as your wording before the video is posted. Numbers on screen must be real (from the owner or the
   footage), never invented.
4. **Skin.** `--skin dark` (default: neutral dark panels, white text, yellow keywords) for personal videos;
   `--skin brand --brand <slug>` for a brand's videos (its colours and fonts from `brands/<slug>/brand.json`). A brand's
   videos also follow its `BRAND.md`: keep-outs, and permission from anyone visible.
5. **Check:** `.venv/bin/python effects/fx.py sheet <video> <name>@<when> [...]` (a contact sheet in seconds, path
   printed). Read it and fix the moment or settings first.
6. **Render:** `.venv/bin/python effects/fx.py apply <video> <name>@<when> [...]`, which writes
   `<shoot>/Style Tests/<video>_<effects>_vN.mp4` and never overwrites. Open it in Video Review. Then refresh the
   tracker (`library/README.md`).

## In a new edit (when they make sense)
Effects go on the picture **before** captions and titles, through each builder (`STYLES.md` shows the exact call):
- **Talking Head Classic:** an `effects=[...]` list in the build call. Times and words are in the edit's time.
- **Hands-On Classic:** `"effects": [...]` in the edit spec, e.g. `["paper-tear@fresh", {"effect": "news", "at": [3.0, 7.5], "set": {"style": "magazine"}}]`, with `"effects_skin": "brand"` for a brand's video.
- **Fast Cut:** `EFFECTS = [...]` at the top of the script; it renders scenes, then effects, then captions.
- **Anything else:** `core.effects_pass(picture, effects, words=..., audio=..., skin=...)` on a caption-free picture.

**When an effect earns its place.** Put one in the plan only where it lands on something said, and say which moment and why. The owner decides.
- Hook, bold claim or payoff word: `spotlight`, `impact-frame`, `letter-dive`, `paper-tear` (as an opener), `cover-story`, `glass-type`, `arch-text`, `digital-zoom`.
- A list of changes, steps or wins: `apple-toggles`, `todo` (or `/checklist`), `head-stack`, `sketch-words`, `phone-mockup`.
- A real number said on camera: `glass-widgets` (stat), `post-wall` (a real count), `chart-grow` (with real `values`). Never one without a real number.
- A quotable line: `news` (newspaper / blog / magazine), `typewriter`, `headline-wall`, `ui-world`.
- Section change or a cut between two shots (transitions): `zoom-through` (on a hard cut), `paper-tear`, `blade-slice`, `letter-dive`, `layer-explode`, `dolly-zoom`, `frame-break`.
- Reflection or a turning point: `rack-focus`, `dolly-zoom`, `spotlight`.
- Behind the scenes or how it was made: `timeline`, `live-cursor`, `predict-keys`, `voice-note`, `code-body`, `pull-back`, `ui-world`.
- Energy or a fun beat: `clone-row`, `orbit`, `head-stack`, `doodle-boil`, `paper-cut`, `couch-wall`; `blow-away` as an ending.
- Talking about time or money: `day-dial`, `banknote` (never an invented amount).
- Showing other footage while talking about it: `green-screen` (another clip or a photo in a card above the speaker).
- A call to comment: `comment-drop` (any username or comment text is your wording; flag it).

**How many.** At most one effect every 10–15 s, never the same kind twice in a row, and each one lands on something said. Talking Head Classic is plain by design, so 1–2 per video at most. Fast Cut can take more. Brands set to restrained (`"effects": {"restrained": true}` in brand.json) stay quiet: paper-tear, news (magazine), letter-dive, rack-focus, typewriter, sketch-words. Use tech-looking ones (code-body, timeline, live-cursor, predict-keys) only if the owner asks.

**Transitions.** In an edit, give a transition a window that spans the cut: `zoom-through` with `peak` set to the cut (seconds into its window), `paper-tear` with the cut about 30% in, `blade-slice` about 80% in, `letter-dive` about halfway.

**Flag the text.** Before the video is posted, list every word on screen that the speaker didn't say: labels, titles, usernames, a masthead, the default UI labels ("Editor", "Working on", "Rendering", "POSTS"). Each effect's `SAMPLE["note"]` says `CLAUDE-WROTE` when its default shows wording like that.

**Check before rendering:**
- Cards that sit under the chin (apple-toggles, todo, the comment field) can collide with captions. Move them with the `y` setting or turn captions off for that stretch.
- Effects that remove the speaker (blow-away, dolly-zoom, clone-row, layer-explode) need the empty room. Use them when there's a clean shot of the empty set (`plate` setting) or the soft patch won't show.
- Render a sheet of the effect's stretch with captions on, then watch it in Video Review.

## Notes
- The first run on a video prepares it at about 2 s per second of video: a 9:16 crop around the face if it's horizontal, a cutout of the person on every frame (Apple Vision), face boxes and word timings. It's cached in `effects/cache/`, safe to delete. The tracker builds itself the first time (`sh effects/build_helpers.sh`, needs `xcode-select --install`).
- Suggest filming 2–3 s of the empty set before or after a talking take, so the dust, clone and vertigo effects have a real background.
- **Adding an effect:** follow `effects/README.md`, "Add an effect". It stays in review until the owner approves it.
