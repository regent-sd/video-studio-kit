# Effects library

An **effect** is a named visual trick you can put on any stretch of any video: a word glowing behind your head
(`spotlight`), a checklist that ticks off as you say each item (`todo`), a newspaper front page with your line as the
headline (`news`), a fast zoom through a cut (`zoom-through`). There are 42, each with its own slash command
(`/spotlight`, `/todo`, `/news`…) and `/effects` for the whole list and when to use which.

Effects find you in the frame by themselves: on the first run a stretch of video is prepared with a cutout of the
person on every frame, the face box and the words said. So an effect can sit *behind* you (in front of the room), put
a card under your chin, redraw you, or move the camera, and the text it shows is your own words from the clip.

## What's in this folder

| File | What it is |
|---|---|
| `fx.py` | The command line: `list`, `apply` (render a video), `sheet` (a contact sheet, fast), `prep`, `commands` (writes the slash commands) |
| `make_previews.py` | A short preview of each effect on your own footage, plus one contact sheet of them all |
| `core.py` | The engine: preparing a stretch (crop, cutout, face, words), rendering frame by frame, the skins, and the calls the style builders use (`effects_pass`, `render_with_effects`) |
| `catalog/` | One file per effect (`catalog/spotlight.py`…) and shared drawing helpers (`_ui.py`, `_b.py`, `_print.py`, `_cam.py`…) |
| `effectsmap.py` | Writes `<video>.effects.json` beside a finished video, so Video Review shows what's on screen over each stretch |
| `track.swift` | The person tracker (Apple Vision, built into macOS): a cutout and a face box on every frame |
| `build_helpers.sh` | Builds the tracker on your Mac into `cache/bin/track` (setup runs it; the effects also run it the first time) |
| `cache/` | Prepared stretches, the built tracker and quick sheets. Made on your Mac, never in git, safe to delete |

## Use one

**Ask Claude.** Type the effect's command with a video and a moment, or just say it:

```
/spotlight "2026-03-14 Kitchen Remodel/Raw/Camera/clip_0012.mp4" at "finally"
/todo <video> at 4.0-9.5
"put a newspaper effect on the line about opening day"
/effects                      the list, and which one suits a moment
```

**On any video, from the command line** (Claude runs these for you):

```
.venv/bin/python effects/fx.py list
.venv/bin/python effects/fx.py sheet "<video>" spotlight@finally                 # a contact sheet in seconds, to check first
.venv/bin/python effects/fx.py apply "<video>" spotlight@finally todo@4-9.5 --set todo.title="Today"
```

- `<when>`: `7.2-10.6` (seconds), `7.2` (a start; the effect's own length), `finally` (starts on that word),
  `finally+4` (on that word, 4 s long), or nothing (the whole video).
- `--from S --to E` trims a long raw clip first. `--grade camera` or `--grade pov` gives camera originals a light grade.
  `--cx`, `--zoom` crop a horizontal source by hand (default: follow the face).
- `--skin dark` (the default) or `--skin brand --brand <slug>` (see Skins below).
- `--set key=value` changes a setting (`effect.key=value` when there are several effects). Values can be JSON.
- Output: `<shoot>/Style Tests/<video>_<effects>_vN.mp4`, never overwriting. The sound is untouched. Each export is
  logged in `<content folder>/Footage Log/effects-applied.json`, so the video tracker knows which raw seconds it used.

**In a new edit.** The style builders put effects on the picture *before* captions and titles, in the edit's own time
(so `@finally` finds the word in the edit's transcript). `STYLES.md` shows each builder's exact call:

| Builder | How |
|---|---|
| Talking Head Classic | an `effects=[...]` list in the build call |
| Hands-On Classic | `"effects": [...]` in the edit spec, and `"effects_skin"` (`dark`, `brand` or `brand:<slug>`) |
| Fast Cut | `EFFECTS = [...]` at the top of the script: scenes, then effects, then captions |
| Anything else | `core.effects_pass(picture.mp4, effects, words=..., audio=..., skin=...)` on a caption-free picture, or `core.render_with_effects(...)` for frame-by-frame renderers |

Each item can be `"name@when"`, `("name", start, end)` / `("name", start, end, {settings})`, or
`{"effect": name, "at": "word+4" or [start, end], "set": {...}}`.

**Previews on your own footage.** Point it at any folder of clips. It picks a talking clip (the steadiest, biggest
face) for most effects and a clip without a face as the second shot for the transitions:

```
.venv/bin/python effects/make_previews.py --footage "<a shoot>/Raw" --out "<a shoot>/Style Tests/Effects"
.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --brand my-brand --only spotlight,news,todo
```

It writes `FX_<effect>.mp4` for each, `contact.jpg` (a still of each) and `previews.json` (which clip and seconds
each used, and which show wording Claude wrote). All 42 take a while; `--only` a few first, or `--sheet-only` for the
contact sheet alone.

## Skins

Every effect draws its cards, words and glows in a skin:

- **Dark** (the default): neutral dark panels, white cards and text, yellow keywords, SF Pro. Good for personal videos.
- **Brand**: the colours and fonts of a brand in `brands/<slug>/brand.json` (background, surface, text, accent,
  highlight, dark…; title, heading, body, caption and number fonts). `--skin brand` uses the default brand
  (`default_brand` in `studio.json`); `--brand <slug>` picks one.

A brand with `"effects": {"restrained": true}` in its `brand.json` gets only the quiet effects unless you ask:
paper-tear, news (magazine), letter-dive, rack-focus, typewriter, sketch-words. Its `keep_out` list and
`people` rules apply to anything an effect shows, as to any other shot.

## Rules built in

- **Only real numbers on screen.** Any setting that shows a number (a stat, an amount, a count) defaults to none.
  Counts of what's actually on screen, the video's own size and frame rate, elapsed time and today's date are allowed.
- **Your own words by default.** Text comes from the transcript (the first key word said in the window, or the
  sentence). Any wording Claude writes goes in a setting and gets flagged before posting. Each effect's `SAMPLE["note"]`
  says `CLAUDE-WROTE` when its preview shows Claude's wording (a default label such as "Editor" or "Working on").
- **Exports go to Style Tests** and never overwrite. A new effect stays in review until you approve it (below).
- Effects work best on footage *before* captions are burned in: on a finished video, a burned-in title box gets
  treated as part of the room, and effects that darken or redraw the frame darken its captions too.

## Transitions

Four effects work as a **transition** between two shots. In an edit, give the effect a window that spans the cut, and
the cut is hidden at its peak:

| Effect | Where the cut goes | What you see |
|---|---|---|
| `zoom-through` | its `peak` (the middle by default; set `peak` to the cut's second in the window) | a fast push in with radial blur and a flash, then out into the next shot |
| `paper-tear` | about 30% in, while the sheet covers the frame | a paper sheet with your word drops, then tears open on the next shot |
| `blade-slice` | about 80% in, as the pieces snap back | a blade flash slices the frame; the pieces slide apart and snap shut on the next shot |
| `letter-dive` | about halfway, while the word is small | the shot shrinks into the letters of a word, then the camera dives into a letter |

`make_previews.py` shows each of them over a real cut between two clips.

## The effects

Lengths are the defaults when you give only a start. Every setting is in the effect's slash command
(`.claude/skills/<effect>/SKILL.md`) and in `fx.py list`.

### On top of you

| Effect | What it does | When it fits | Length |
|---|---|---|---|
| `apple-toggles` | iPhone settings switches under your face that flip on as you say each word | You list changes or wins | 5 s |
| `comment-drop` | A comment is typed and posted, comment cards drop in from the top, and the word lands huge behind your head | A call to comment (any username or comment you write gets flagged) | 5 s |
| `glass-widgets` | Frosted-glass widget cards (stat, chart, progress, ring, profile, pill) float around your head | A real number you give (the stat card); a creator or tech feel | 5 s |
| `head-stack` | Word stickers drop onto your head as you say them and stack into a wobbly tower | You list a few words; a fun beat | 5 s |
| `live-cursor` | Design-app selection box with its real pixel size, and a named cursor that drags it into place | Behind the scenes, how this was made (ask first: tech look) | 4 s |
| `news` | A newspaper / blog / magazine front page: your words as the headline, you as the photo, your key word highlighted | A quotable line, a bit of news | 4.5 s |
| `paper-tear` | A paper sheet with your word drops over the frame, then tears open to reveal you. **Transition.** | An opener, a section change; a transition | 3 s |
| `phone-mockup` | A phone floats beside you; its app sheet checks off your words one by one, then taps Done | You list steps or wins | 5 s |
| `predict-keys` | A phone keyboard slides up and types your words key by key, tapping the predicted word as you say it | Behind the scenes, typing a question (ask first: tech look) | 5 s |
| `timeline` | An editing timeline from this clip (thumbnails, captions, colours, waveform) with your footage in a viewer | How this was made (ask first: tech look) | 5 s |
| `todo` | A checklist card under your chin that ticks off each item as you say it | You list changes, steps or wins | 5 s |
| `typewriter` | Your words type onto the screen letter by letter as you say them, with a blinking caret | A quotable line | 5 s |
| `ui-world` | The top of the frame turns into a light app: a prompt box types your words, then sends | A question or prompt you say; behind the scenes | 5 s |
| `voice-note` | A voice-message bubble above your head with your face, a live waveform of your voice and the running time | A personal aside, a message to the viewer | 4 s |

### Behind you (uses the cutout)

| Effect | What it does | When it fits | Length |
|---|---|---|---|
| `arch-text` | Your line arches over your head like a rainbow, behind you; rises as your hand goes up, words light as you say them | A hook line, best said with a hand raised | 3 s |
| `chart-grow` | A glowing line chart draws itself across the room behind you, the last point lit up | A real trend you give (with its real values); without values it's a decorative rising curve | 4.5 s |
| `couch-wall` | The room behind you becomes a tilted wall of big rounded video tiles playing other moments of this video | Energy; 'there's a lot more where this came from' | 4.5 s |
| `cover-story` | A magazine cover: a huge serif masthead behind your head, cover lines of your words, today's date | A bold claim or payoff word | 5 s |
| `day-dial` | A huge clock dial behind your head: hour numerals, your word around the rim, a sweeping hand | Talking about time: a day, a routine, a deadline | 4 s |
| `doodle-boil` | A boiling hand-drawn chalk outline around you, with crayon doodles and your word around your head | A light, fun beat | 4 s |
| `glass-type` | Big 3D glass letters of your word stand behind your head and refract the room | A hook or payoff word | 4 s |
| `green-screen` | Creator green-screen layout: you cut out low in frame over a dark backdrop, a card of other footage above you | Showing other footage or a photo while you talk about it | 5 s |
| `headline-wall` | Your lines pop up around your head as a post, a search, a sticky note, a clipping, a chat bubble and a headline | A quotable line; reactions | 5 s |
| `orbit` | A ring of thumbnail cards orbits your head in 3D, behind you at the back, in front at the front | Energy, a fun beat | 5 s |
| `post-wall` | A wall of post tiles pops in behind you on a dark backdrop, with a header counting the tiles | A real count of posts or items | 4.5 s |
| `sketch-words` | Hand-written marker words and doodles appear on the room as you say them | A light explainer, a few words | 4 s |
| `spotlight` | Room goes dark, you stay lit, a glowing word sits behind your head | A hook, a bold claim or a turning point | 3.5 s |

### You, restyled

| Effect | What it does | When it fits | Length |
|---|---|---|---|
| `banknote` | Your face engraved into an ornate banknote that slides in with a 3D tilt | Talking about money or value (never an invented amount) | 4 s |
| `code-body` | You, rebuilt from monospaced characters of your own words, with code rain behind | Behind the scenes, tech (ask first: tech look) | 3 s |
| `impact-frame` | Black-and-white comic ink version of you with speed lines and a big word | A punchline, a hook or payoff word | 1.6 s |
| `paper-cut` | Scrapbook collage: you as a die-cut sticker on torn paper scraps, your word in ransom-note letters, stop-motion | A playful title, a fun beat | 4 s |

### Camera and body tricks

| Effect | What it does | When it fits | Length |
|---|---|---|---|
| `blade-slice` | A blade flash slices the frame diagonally; the pieces slide apart, hold, then snap back with a shake. **Transition.** | A section change; a transition | 1.8 s |
| `blow-away` | You crumble into dust and blow away, leaving the empty room, then reassemble | An ending, or something being gone | 4 s |
| `clone-row` | Copies of you slide out from behind you and recede into the distance on both sides | Energy; doing many things at once | 3.5 s |
| `digital-zoom` | Camcorder digital punch-in to your face in quick steps, with a glitch on each step and a REC viewfinder | A hook or a reveal word | 3.5 s |
| `dolly-zoom` | Vertigo shot: you stay put while the room zooms in or out behind you, then eases back | A realisation or turning point; a section change | 2.5 s |
| `frame-break` | The shot shrinks into a floating 3D card, then you break out of it: head and shoulders in front of its edges | A section change; breaking out of a routine | 4 s |
| `layer-explode` | The shot splits into 3D layers (room, you, a word) that spread apart and turn, then fly back together | A section change | 3.5 s |
| `letter-dive` | A giant serif word on paper with the video playing inside the letters; the camera dives into a letter. **Transition.** | A hook word, a section change; a transition | 3.2 s |
| `pull-back` | The camera pulls back: your clip plays in an app window, a 'Working on' card ticks off steps, a render bar fills | Behind the scenes, steps being worked through | 6 s |
| `rack-focus` | Focus pull: room blurred behind you, then the focus shifts to the room (you blur), then back | Reflection, a turning point (quiet) | 4 s |
| `zoom-through` | Fast zoom-through whoosh: accelerating push into your face with radial blur and a flash, then back out. **Transition.** | A hard cut between two shots; a transition | 1.2 s |

Other names that work: `checklist` (todo in its compact style), `vertigo` (dolly-zoom), `newspaper` and `press-front`
(news), `magazine` and `cover` (cover-story), `dust` (blow-away), `clones` (clone-row), `ascii` (code-body),
`toggles` (apple-toggles), `widgets` and `glass` (glass-widgets), `impact` (impact-frame), `pullback` (pull-back),
`greenscreen` (green-screen), `chart` (chart-grow), `headlines` (headline-wall), `doodle` (doodle-boil),
`ransom` (paper-cut), `phone` (phone-mockup), `prompt` (ui-world), `camcorder` (digital-zoom), `zoom-cut`
(zoom-through), `orbit-ring` (orbit).

## In review

New effects you add stay here until you approve them for reuse. Don't put one in an edit without saying it's new.

In review: none yet.

## Add an effect

1. Copy the closest `catalog/<name>.py` to `catalog/<new_name>.py` (hyphens in the name become underscores). Set
   `NAME`, `KIND` (`cards`, `behind`, `restyle` or `camera`), `ABOUT` (one line), `DUR` (default length), `PARAMS`
   (settings, each with a comment saying what it does) and `render(c)`, which gets one frame's `Ctx` (the frame, the
   cutout, the face box, the words, its time in the window, the settings and the skin) and returns the new frame.
2. Give it a `SAMPLE` (preview settings, and a `note` saying who wrote any text it shows).
3. Check it: `.venv/bin/python effects/fx.py sheet <a clip> <name>@<when>`, then
   `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only <name>`.
4. Make its slash command: `.venv/bin/python effects/fx.py commands`.
5. Add it to the table above and to **In review**. It moves out of review when you approve it.

## Effects maps (what's on screen, in Video Review)

`effectsmap.py` saves `<video file>.effects.json` beside a finished video. Video Review then shows a row between the
ruler and the frames: one block over each stretch with something on screen besides plain footage (a Fast Cut layout,
a library effect, a hook title, an end card), named the way the Glossary names it. Click a block to jump there.

It happens by itself: the builders keep a build record of each render (`library/buildrecord.py`), and when a
finished file is put in place with `library/finish.py` (or `library/footage.py index` finds a video without a map),
`effectsmap.py VIDEO` reads that record after checking the video's picture is the render's, bit for bit.

```
.venv/bin/python -I effects/effectsmap.py "<video>"            # from its build record
.venv/bin/python -I effects/effectsmap.py "<video>" --show     # print the map
.venv/bin/python -I effects/effectsmap.py "<video>" --log render.log --vocab fastcut    # a render printout instead
```

It refuses, and writes nothing, unless the records are this video's own (same length, same picture, or scene
changes that match the video's shot changes). `--dry-run` checks without writing, `--replace` makes a map again.
When a video moves (to `Finished/` when approved), move its `.effects.json` with it, as with the notes and sound map.

## How it works

1. **Prep** (`core.prep`, cached in `cache/<key>/`): the stretch is conformed to 1080×1920 at 30 fps. A horizontal
   source is cropped 9:16 around the face. The tracker (`cache/bin/track`, Apple Vision) makes a cutout of the person on
   every frame and finds the face. Word timings come from the Footage Log transcript (`<clip>.words.txt`) if there is
   one, else whisper.cpp (`whisper-cli` with the model in `studio.json`'s `whisper_model`, default
   `~/.cache/whisper.cpp/ggml-base.en.bin`). An 18 s stretch preps in about 40 s.
2. **Render** (`core.render`): frame by frame, each effect's `render(c)` gets a `Ctx` and returns the new frame. Frames
   outside every window pass through.
3. **The empty room** (`Subject.plate()`) is averaged from the frames where the person wasn't, and the rest is filled
   in from around it. When someone fills the frame the whole time, it's soft. Effects that remove the person
   (blow-away, dolly-zoom, clone-row, layer-explode) look best with `--set plate=<photo of the empty set>`, so film
   2–3 s of the empty frame at the start or end of a talking take.

Needs: ffmpeg, Python with Pillow, numpy and scipy (the kit's `.venv`), the Xcode command line tools (`swiftc`, for
the tracker) and macOS 14 or later. whisper.cpp only for clips without a transcript.

## What to say to Claude

| Say | What happens |
|---|---|
| `/effects` | the list, and which effect suits a moment |
| `/<effect> <video> at "<word>"` | that effect on that video, checked on a sheet, rendered to Style Tests |
| "preview the effects on my footage" | `make_previews.py` on a shoot's `Raw` folder |
| "add <effect> to this edit at <moment>" | the effect goes in the builder's effects list, before captions |
| "approve <effect>" | it moves out of **In review** |
