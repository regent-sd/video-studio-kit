# Video Studio Kit

A complete short-video studio you run by talking to Claude Code on your Mac. You film; Claude logs your footage, plans each edit with you, builds it in a named style with effects, captions and real sound effects, and you review every cut on a local notes page before you approve it.

What's inside:

- **Three editing styles**: Fast Cut (a new layout every 1–2 s, in a Dark or your Brand skin), Talking Head Classic (title box, word-by-word captions, punch-in jump cuts) and Hands-On Classic (warm grade, hands at work, hook title, music bed, end card). `STYLES.md`
- **40+ visual effects and transitions**, each with its own slash command. `effects/README.md`
- **A sound-effects pass** with real recorded sounds placed on the right frames, checked by ear-substitute tools so nothing lands on a word. `sound/README.md`
- **Video Review and the Studio page**: watch a cut, press N, type a note at that exact moment; Claude applies your notes as a new version. `review/README.md`
- **Footage Log**: every raw clip transcribed and described, searchable by what's in it and what's said. `library/README.md`
- **Asset Library**: a tagged, searchable catalog of your photos, logos and print pieces. `assets/README.md`
- **Your brand and voice**: colours, fonts, logo, keep-out list and how you sound, set up by a short interview. `setup/BRAND-SETUP.md`
- **Your voice clone**: made by you in the free VoiceStudio app, used by Claude for voiceovers from scripts you approve. `setup/VOICE-STUDIO.md`
- **Product walkthrough videos**: narrated how-to videos of your own app, from script to voiceover to scripted screen recording to finished film. `walkthrough/README.md`
- **House rules** that came from many rounds of real editing notes: adopt them, edit them, or start clean. `rules/README.md`

## Get started

1. A Mac with Apple Silicon (M1 or newer) and about 25 GB free.
2. Install Claude Code: https://claude.com/claude-code
3. Put this folder somewhere iCloud doesn't sync, e.g. `~/Developer/video-studio-kit`.
4. Open Claude Code in this folder and say **"set up my studio"**.

`START-HERE.md` walks through what happens next.

## Licenses

The kit's own code and docs: see `LICENSE.md`. The tools it installs (ffmpeg, whisper.cpp, Earshot, Real SFX, HyperFrames, Remotion, VoiceStudio and its models) each keep their own license; `setup/INSTALL.md` lists them. Remotion needs a paid license for companies of more than 3 people. Stock demo clips are downloaded by you from their sites under each site's license (`demo/README.md`).
