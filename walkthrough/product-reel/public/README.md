# public/

Files the reel uses, by name from `src/reel.json` and `src/theme.json`:

| File | Put here |
|---|---|
| `voiceover.wav` | the voiceover, levelled to about -16 LUFS |
| `music.wav` | the music bed, cut to the reel's length and faded out |
| `clips/*.mp4` | screen recordings for the device frames |
| `logo.png`, `fonts/` | copied in by `walkthrough/rig/new_reel.py` from your brand |

In the kit's own copy this folder stays empty: start a reel with `new_reel.py`, which copies the template to your work folder first.
