# Video styles

The named looks for your reels. Say the name to use one: "make this **Fast Cut**", "do the bake in **Hands-On Classic**". If a request doesn't name a style, Claude asks which one before editing. None of them is the default; each is one option.

| Style | What it looks like | Good for | Built with |
|---|---|---|---|
| **Fast Cut** | The layout changes every 1–2 seconds: split screens, floating cards, big numbers, photo grids. Captions show 1–3 words at a time. | Talking or explaining: a story, a how-to, results | `styles/fastcut` |
| **Talking Head Classic** | Talking head and B-roll, a white title box, yellow word-by-word captions, jump cuts that punch in | Talking to camera: tips, a story, an update | `styles/talking-head` (`reelkit.py`) |
| **Hands-On Classic** | Bright, warm grade; hands at work; a hook title, short captions in brand blocks, a music bed, an end card | Making something: a recipe, a build, a process | `styles/hands-on` (`build_reel.py` and an edit spec) |

**Skins.** Fast Cut comes in two skins: **Dark** (SF Pro type, dark split-screen panels, white cards, yellow keywords) and **Brand** (your brand's colours, fonts, caption style and grade, from `brands/<slug>/brand.json`). Personal, talking-to-camera content gets the Dark skin; anything for a brand gets the Brand skin. You can also name it: "Fast Cut, Brand skin".

Sample contact sheets of each style and skin, made from your own footage: `.venv/bin/python styles/make_samples.py --footage "<shoot>/Raw" --out "<shoot>/Style Tests/Samples"` (or `demo/run_samples.py` for the demo shoot).

`styles/README.md` lists every file and command. Reel covers for any style: `styles/cover.py`.

---

## Fast Cut

### Rhythm
- The layout changes every 1–2 seconds, cut on the first sound of a word. Hard cuts, no transitions.
- Don't use the same layout twice in a row. About half the time is graphics, half is footage.
- Open on the hook: a split screen with the title on top and the payoff footage below.

### Layouts
1. **Split screen.** A graphic panel on top (1080 × 960), footage below. The caption sits on the seam.
2. **Full footage.** A talking head or B-roll. The caption goes on the chest, or below the face.
3. **Card.** One floating card on a plain background. It rises in about 0.45 s, tilted 20–30°, settles to about 6° with a soft shadow, and drifts slowly. Rows, tags and check marks build as the words are said.
4. **Big number.** Counts up as it's said (a weight, a temperature, a number of months), often with a ring or dial.
5. **Explainer.** A tiny diagram: two options with a check and a cross, a scale, a before and after.
6. **Punch-in.** The same moving footage, about 1.35× tighter, as a quick change of view. Use this instead of still photos: a stack of stills reads as static and confusing.
7. **Mosaic.** A 3 × 4 grid of stills popping in about 0.06 s apart.
8. **End card.** Logo, a line, the handle and the brand's end line. Quiet: no chime under it.

### Motion
- Tags and stickers pop in with a small overshoot. Counters count up.
- A tag over footage stays up for at least 1.5 s and matches what's on screen, or it isn't used. A tag up for half a second feels out of place.
- A hard word gets a shake and a colour flash (`reel.full(..., hit_at=t)` or a `Slam`).

### Captions
- 1–3 words. A new caption starts at punctuation, at a pause over 0.35 s, and at every shot change.
- A caption belongs to one shot. It never carries across a cut, because it would be drawn again in the next layout's spot and look doubled. A caption that starts within 0.4 s of a cut waits for the next shot.
- Whisper sometimes stretches a word across a pause, so each word is capped at 0.7 s before grouping.
- Keywords are highlighted. Each caption pops in over 0.14 s.
- Never over a face. Nothing important above y 220 or below y 1470 (the app's own bars cover them).
- Caption timing comes from the word transcript; cut points come from the sound level.

### Sound
- The speech is untouched: the same cuts as the edit, crossfaded at each cut, levelled to −14 LUFS.
- Real sound effects, clearly audible but under the voice: a whoosh into card scenes, a pop for tags, ticks for counters, a hit for slams, a click for each check mark. The builder writes these moments to `work/<name>/sfx_events.json` and renders without effects of its own; the sound-effects pass places real recordings on those frames (`sound/README.md`).
- No music by default. Each video gets its own track, one you picked, never one already used (`--music` or `music=`).

### Honesty
- Only real numbers go on screen. Where there's no real number, show a flag ("LOW", "up", a check), never a made-up value.
- Claude flags any text it wrote (a title, a joke, an explainer) so you can approve it before posting. The engine lists every on-screen word nobody said when it renders.
- Check the brand's keep-out list (`brand.json` → `keep_out`). A new crop can bring back something the original framing hid.

### Dark skin
- **Type:** SF Pro (system font), Bold and Heavy.
- **Colours:** dark panels (#08090B to #1E2026) and light backgrounds (#FCFCFA to #EAE9E5). White text with yellow keywords (#FFD60A), red for bad (#FF3B30), green for good (#28BE69).
- **Cards:** white cards with grey placeholder rows that fill in.

### Brand skin
- **Colours:** the brand's `background` for every plain background, `text` for words, `accent` for tags and the hook's accent line, `highlight` behind keywords. Never a dark or accent colour as a full background.
- **Type:** the brand's `title` font for titles and big numbers, `heading` for card titles, `caption` for captions.
- **Captions:** the brand's `captions` settings: blocks or outlined text on footage, plain text on backgrounds, keywords highlighted or in the accent colour.
- **Footage:** the brand's `grade` (warm, neutral or cool).

### How to make one (for Claude)
1. Read the brand (`brands/<slug>/BRAND.md`, `brand.json`), `guides/storytelling.md` and the house rules. Find the talking clip and the B-roll in the Footage Log.
2. Copy `styles/fastcut/example.py` to the shoot's work folder or a new script, and write the reel by hand:
   - the **edit**: `fc.Edit([fc.piece(talk, a, b), ...], tail=2.5)`. Take phrase cut points from the sound, never inside a word: `words.cut_points()` (see `make_edit()`), or `reelkit.phrase(clip, "first words", "last words")`. Voice over B-roll: `fc.piece(broll, t, t + d, audio=(talk, a))`.
   - the **scenes**, in order, each starting on a caption start (`reel.caption_starts()`): `reel.split()`, `reel.full()`, `reel.punch()`, `reel.broll()`, `reel.tag()`, `reel.card()`, `reel.card_split()`, `reel.graphic()`, `reel.end()`. Graphics are in `styles/fastcut/graphics.py` (`Hook`, `ListPanel`, `Checklist`, `StatCard`, `BigNumber`, `Compare`, `Slam`, `Mosaic`, `EndCard`); rows tick and numbers count at the moment the word is said (`reel.word_time("880")`).
   - **effects** (the effects library), where they land on something said: `EFFECTS = ["spotlight@stronger", ("checklist", 12.0, 17.5)]` in reel time. The engine draws the scenes, puts the effects on, then the captions. `.claude/skills/effects` says when each fits.
3. `--plan` lists the scenes, rhythm notes and any on-screen text nobody said. `--sheet` draws one frame per scene in under a minute. Check it, fix, then run the full render (about 40 s per 20 s of reel). `--mux` redoes only the sound.
4. Run the sound-effects pass on the render (`sound/README.md`), using `work/<name>/sfx_events.json`.
5. The video lands in `<shoot>/Style Tests/<name>_vN.mp4` (never over an existing file) with its sound and effects maps; the build record stays in the work folder. Open it in Video Review. Apply notes as a new version, and move it to `Finished/` once approved (`guides/after-approval.md`).

---

## Talking Head Classic

The look: a talking head with B-roll, a white title box at the start, white word-by-word captions with the word being said in yellow (Avenir Next Condensed Heavy, black outline), jump cuts that alternate a 1.1× and a 1.25× punch-in, the voice at −14 LUFS.

- **Cuts:** every cut sits in a pause found in the sound, never inside a word. Whisper's word times can be off by more than half a second, so `reelkit.phrase()` finds the pause from the sound level.
- **Check every build:** `styles/talking-head/verify.py <video>` re-transcribes the reel and lists any word that differs from the plan, and checks each cut lands in a pause. A shortened word ("tank" for "tanked") is a clipped word.
- **Captions:** 1–3 words from the transcript, at y 1330, never over the face. Fillers (um, uh) are left out of the captions.
- **Sound effects** are light touches: a whoosh on the title box, a hit on a big statement or number, a riser into the payoff. Jump cuts and B-roll with their own sound get none (`sound/README.md`).
- **Visual effects:** `build(..., effects=["spotlight@stronger"])` puts them on before the captions (reel time). One or two per reel at most; keep cards clear of the captions at y ≈ 1330.

### How to make one (for Claude)
1. Copy `styles/talking-head/example_reel.py` and write the recipe: the phrases in order (`rk.phrase(talk, "first words", "last words")`), one segment each, the talking head alternating zooms (`rk.jump_cuts()` does this), B-roll over a phrase (`rk.cam()`, `rk.pov()`), the title box (`rk.title()`), labels or a stats card where they help.
2. Run it. The reel goes to `<shoot>/Style Tests/<name>_vN.mp4` with its words file, maps and build record.
3. Run `verify.py` on it. Fix any clipped or missing word before anyone watches it.
4. Sound-effects pass, then Video Review.

---

## Hands-On Classic

The look: bright and airy with a slight warmth (the brand's grade), first-person close-ups of hands at work, a hook title in the first second, short captions in brand blocks (1–3 words, timed to the action), the footage's own sound up front with a music bed under it, and an end card with the logo. 20–35 s for reels.

- **Hook in the first second.** Open on the strongest picture; the payoff shown first works.
- **Sound:** the footage's own sound stays up front (pours, knocks, machines); music sits underneath and ducks under any voice. No talking unless asked: swap a shot's sound for a speech-free stretch of the same clip (`audio`).
- **Cut voice only in pauses** (`say` in the spec cuts by what's said, from the sound level). Re-transcribe the export to check (`verify.py` works on any video with a words file).
- **Light faces** the camera left dark (`face_light`, amount about 0.6). **Never put captions over a face** (`caption_y`).
- **Sound effects** only where the picture is silent: the hook title, text pop-ins, the end card. The footage's own sound always wins over library sounds.
- **Visual effects:** `"effects": [...]` in the spec, in the brand skin. Keep it restrained: paper-tear, news, letter-dive, rack-focus, typewriter, sketch-words.
- **Music:** a track you picked for this video (`music_file`), fitted to the length so it ends on its own ending. Never reuse a track. No track, no music.
- **People and keep-outs:** anyone clearly visible has said yes; check the brand's `keep_out` list.

### How to make one (for Claude)
1. Look at the clips (contact sheets) and read their transcripts. Start from `styles/hands-on/example-spec.json`, or `build_reel.py --starter "<shoot>"` for a spec built from the clips.
2. Write the spec (`styles/hands-on/SPEC.md` has every field): segments in story order, 2–5 s each, the hook, captions, tags, a counter only for a real number, the end card.
3. Build: `.venv/bin/python styles/hands-on/build_reel.py <spec.json>`. It writes `<shoot>/Style Tests/<name>_vN.mp4`, the words file, the maps and the build record.
4. Check a contact sheet of the export and re-transcribe it if anything is said. Sound-effects pass, then Video Review.

---

## Reel covers

`styles/cover.py <video> --at <seconds> --title "TWO|LINES"` makes a 1080 × 1920 cover from a frame, in the Dark look or the brand's (`--skin brand`), with everything that matters inside the profile grid's 3:4 band (y 240 to 1680). `--pop` puts the person in front of the title. It also writes a preview of the grid crop.
