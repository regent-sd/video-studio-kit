# Hands-On Classic edit spec

A spec is one JSON file per reel. The spec *is* the edit: build it again any time and you get the same reel.
`example-spec.json` is a full example for the demo shoot; `build_reel.py --starter "<shoot>"` prints one made from a shoot's clips.

```
.venv/bin/python styles/hands-on/build_reel.py my-reel.json            # -> <shoot>/Style Tests/<name>_vN.mp4
.venv/bin/python styles/hands-on/build_reel.py my-reel.json --out FILE  # somewhere else (never overwrites)
```

## Reel fields

| Field | What it does |
|---|---|
| `name` | File name stem of the video (a version number is added: `_v1`, `_v2`…). Default: the spec's file name. |
| `notes` | Free text: what the reel is, what was decided. Not used by the builder. |
| `shoot` | The shoot folder: `"2026-03-14 Kitchen Remodel"`, a path, or just a title (`"Demo Shoot"` finds the newest shoot with that title). |
| `brand` | `brands/<slug>`: colours, fonts, logo, end line and grade. Default: the default brand. |
| `sources` | `{alias: {"path": ..., "camera": "cam" or "pov", "grade": ...}}`. `path` is a file name or a path inside the shoot's `Raw/` (`"POV/hands.mp4"`). `camera: "pov"` is a head-mounted or glasses camera (gentler sharpening). `grade`: `"window"` (bright window behind: highlights roll off), `"none"`, or another look (`warm`, `neutral`, `cool`, `punchy`). |
| `source` | One clip for every segment, instead of `sources`. |
| `caption_style` | `"block"` (words on a block of the brand's background colour) or `"plain"` (white with a soft shadow). Default: the brand's `captions.on_footage`. |
| `music_file` | A track you picked for this video: a file in the music library (`studio.json` → `music_library`) or a path. `"track.wav@12.5"` starts 12.5 s in. A list plays the tracks in order (for long videos); only the last is cut. No `music_file`, no music. |
| `music_level` | Music volume under the footage sound (default 0.30). |
| `voice_duck` | Music volume while someone speaks (default 0.12). |
| `word_fixes` | `{"heard": "meant"}`: words the transcript gets wrong, fixed in the captions. |
| `fx` | Reel-level graphics (same types as a segment's `fx`). A negative `start` counts back from the end: `{"type": "endcard", "start": -2.5}`. |
| `effects` | The effects library, in reel time, put on before the graphics: `["paper-tear@0-1.2", {"effect": "news", "at": [3.0, 7.5]}]`. `effects/README.md` lists them. |
| `effects_skin` | Default `brand:<the spec's brand>`. |

## Segment fields

Each segment is one shot, in reel order.

| Field | What it does |
|---|---|
| `src` | Alias from `sources` (default `"source"`). |
| `a`, `b` | Start and end, in the clip's own seconds. |
| `say` | `["first words", "last words"]`: instead of `a` and `b`, cut the sound from the first words through the last, with cut points found in the pauses (never inside a word). With `audio` from another clip, put `say` inside `audio`; the picture then runs from `a` for as long as the words take. |
| `speed` | Playback speed: 2.5 for a time-lapse feel, 0.5 for slow motion. |
| `hold` | Seconds to freeze the last frame. |
| `zoom` | `[x, y, w, h]`: a crop in source pixels (9:16) instead of the centre crop. |
| `pullout` | Show the whole wide frame inside 9:16 over a blurred fill. |
| `blur_top` | Soften the top of the frame (hair across a glasses lens). |
| `face_light` | `{x, y, rx, ry, amount}`: lift a face the camera left dark (output pixels; amount about 0.6). |
| `audio` | Take this shot's sound from elsewhere: seconds in the same clip, or `{"src": alias, "t": seconds}` (voice over B-roll), or `{"src": alias, "say": [...]}`. |
| `voice` | The sound is speech: clean-up EQ and compression, music ducks under it, captions can follow it. |
| `low_cut` | A high-pass in Hz for a hummy room (e.g. 160); with `voice`, a stronger clean-up chain. |
| `voice_clean` | The sound was cleaned ahead of time: skip the builder's voice chain. |
| `mute` | No sound under this shot (the music, if any, carries on). |
| `subs` | Word-for-word captions from the sound's transcript (`<clip>.words.txt`). |
| `caps` | Short captions you write: `[["text", start offset, end offset or null]]`; `"|"` breaks a line. |
| `caption_y` | Centre line for this shot's captions (move them off a face, e.g. 1420). |
| `fx` | Graphics on this shot: `[{"type": ..., "start": offset, "end": offset or null, ...}]`. |

## Graphics (`fx` types)

| Type | Fields | What it is |
|---|---|---|
| `hook` | `text` (`"|"` breaks a line), `sub`, `panel` | The big title in the first second, in the brand's title font. `panel: true` puts it on a block of the background colour, for bright footage. |
| `caption` | `text`, `style`, `y` | One caption (what `caps` makes). |
| `tag` | `text`, `y` | An accent-colour pill that slides in from the left: an ingredient, a temperature, a tool. Up at least 1.5 s. |
| `lower_third` | `title`, `subtitle`, `y` | A name and role, low in the frame. Names only from what the footage or you say. |
| `counter` | `to`, `label`, `count_dur` | A big number counting up, with a label. Real numbers only. |
| `endcard` | `lines`, `brand`, `cta` | The close: the brand's background colour, its logo, a line, its name and its end line (`end_card_line`). Quiet: no chime. |

## Rules the builder keeps

- Every shot is a whole number of frames and the timeline moves on by exactly that, so long edits never drift out of sync.
- Shots are joined with the concat filter (copy-joining scrambles timestamps).
- Sound runs that carry straight on across a picture cut play as one take; neighbours crossfade over 0.1 s at each cut.
- Exports stay under about 28 MB (6 Mbps or less), so they can be sent to a phone.
