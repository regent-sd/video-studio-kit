# Product reel (Remotion template)

A short vertical reel (1080x1920, 10–30 s) for a software product: a headline per beat with a highlighter mark, a screen clip in a phone or browser frame under it, a voiceover and a music bed, and an end card with your logo and a call to action. All in your brand's colours and fonts.

It's a [Remotion](https://www.remotion.dev) project: the video is React code, so every beat is easy to retime, reword or restyle, and Claude can edit it like any code.

**Remotion's licence:** free for individuals, non-profits and companies of up to three people; bigger companies need a paid company licence. Check the current terms at https://www.remotion.dev/license before using it for a business.

## What's here

| File | What it is |
|---|---|
| `src/reel.json` | **What the reel says and shows**: the voiceover and music files, each beat (when it starts, the headline, the sub line, which clip, phone or browser), the end card, the length. Most changes happen here. |
| `src/theme.json` | Colours, fonts, logo and wordmark, written from your brand by `walkthrough/rig/new_reel.py`. |
| `src/Reel.tsx` | Puts the beats, audio and end card on the timeline. |
| `src/Headline.tsx` | The headline with the highlighted words, and the sub line. |
| `src/Device.tsx` | The phone (9:16 screen) or browser frame playing a screen clip, or a placeholder until there is one. |
| `src/EndCard.tsx` | Logo or wordmark, the closing line, the button. |
| `src/theme.ts` | Loads the brand fonts and gives the components colours. |
| `public/` | Your files: `voiceover.wav`, `music.wav`, `clips/*.mp4`, plus the logo and fonts `new_reel.py` copies in. |

## Start one

Don't work in the kit's copy (your voice, music and clips would end up in the kit). Start a copy in your work folder:

```bash
.venv/bin/python walkthrough/rig/new_reel.py launch-reel --brand my-brand [--wordmark "Product name"]
cd ~/Movies/Walkthroughs/reels/launch-reel
npm install                     # Remotion 4.0.545 and React 19 (several hundred MB, with its own headless Chrome)
npx remotion studio             # opens the editor in the browser
```

After changing `brand.json`, run `new_reel.py launch-reel --theme-only` to redo the colours, fonts and logo.

## Fill the slots

1. **Script.** Write one short line per beat, plus a closing line. The headline uses the voiceover's exact words, so the screen and the voice agree. Only real claims and real numbers on screen; flag anything Claude wrote before it's posted.
2. **Voiceover.** Make it in one call for the whole script, one sentence per line (`setup/VOICE-STUDIO.md`), from a script the owner approved. Level it: `ffmpeg -i take.wav -af loudnorm=I=-16:TP=-1.5:LRA=11 public/voiceover.wav`. A person listens before it's used.
3. **Beat times.** Transcribe the take with timestamps (VoiceStudio's `/v1/audio/transcriptions` with `response_format=verbose_json`, or whisper.cpp) and set each beat's `at` to just before its line starts. Set `cta.at` to the closing line and `end` to about a second after the voice ends.
4. **Clips.** Phone-shaped walkthrough takes (`walkthrough/PHONE.md`) or Simulator recordings go in `public/clips/`. Point each beat at one with `"clip": "clips/add.mp4"` and `"clipFrom": 3.5` (seconds into the clip). `"device": "browser"` frames a desktop clip; `"none"` shows the headline alone.
5. **Music.** A licensed track of its own (never one another video used), cut to the reel's length, about 12 dB under the voice and faded out at the end, saved as `public/music.wav`:
   `ffmpeg -i track.mp3 -t <end> -af "loudnorm=I=-28:TP=-3,afade=t=out:st=<end-1.5>:d=1.5" public/music.wav`
6. Set `"voiceover": "voiceover.wav"` and `"music": "music.wav"` in `reel.json`.

## Render and check

```bash
npx remotion render ProductReel out/reel.mp4
.venv/bin/python <kit>/walkthrough/rig/check_film.py out/reel.mp4 --every 1
```

Look at every frame of the contact sheet, then listen to the whole reel. Then give it a sound-effects pass the same way as any other video (`sound/README.md`): a soft whoosh into each beat and a pop on the button, under the voice, never on a word.

Longer or shorter: change `end` (and the beat times); `calculateMetadata` in `src/Root.tsx` sets the length from it. Faster overall: re-time the beats to a faster read rather than speeding up the voice, which makes it sound pitched up.

## What to say to Claude

| Say | What happens |
|---|---|
| "make a product reel for <product>" | `new_reel.py`, a script for you to approve, then voice, beats, clips, render and check. |
| "retime the reel to the new voiceover" | Transcribes `public/voiceover.wav` and sets each beat's `at`. |
| "use the phone take of <walkthrough> in beat 2" | Copies the clip into `public/clips/` and points beat 2 at it. |
