---
name: walkthrough-video
description: "Make a narrated how-to walkthrough video of your own software (a web app, or an iPhone app in the Simulator): script, voiceover in your voice clone, a scripted screen take, title and end cards, captions, click sounds, checks, then publish with your OK. Use for /walkthrough-video, or when asked for a walkthrough, how-to, tutorial or help video of an app, or to re-record one."
argument-hint: <topic> | re-record <name> | phone <name>
---

# /walkthrough-video

Make a walkthrough for: $ARGUMENTS

Follow the playbook in `walkthrough/README.md` ("Make one, step by step"). Use the example as the template: `walkthrough/scripts/example.md`, `walkthrough/rig/takes/example.mjs`, `walkthrough/films/example.film.json`. For an iPhone app or a phone-shaped video, also read `walkthrough/PHONE.md`.

## Before anything else

- Read `studio.json` → `walkthrough` (base URL, work folder, sign-in, test hosts). If it isn't set, ask where the app runs locally and which brand the film is for.
- The app must be a **local, dev or test copy with fake data**. If the only copy is the live product, stop and ask the owner to set up a test copy; never record a production account.
- Check the rig is installed (`walkthrough/rig/node_modules/playwright`). If not, say what `npm install` there will download (Playwright, about 20 MB) and ask before running it.

## The steps, and where to stop for the owner

1. **Plan**: one task, start to finish, 1:00–2:30. List the screens in order.
2. **Look**: start the app; `node walkthrough/rig/explore.mjs <path> <name>` for each screen. Read the snapshots; write selectors from roles and names.
3. **Script**: `walkthrough/scripts/<name>.md` in the example's format, the exact on-screen labels, short plain sentences, spelled the way they're said. **Show it to the owner and wait for their OK.** Flag any claim or number you wrote that they didn't give you.
4. **Demo data**: fake, reset before and after every take. Never click anything that sends a real invite, email, text or payment: hover it instead.
5. **Voice**: `gen_voice.py walkthrough/scripts/<name>.md`. Needs VoiceStudio open (ask the owner to open it); until a clone exists, use `--say` and say so. Fix every line marked CHECK. Only approved scripts; never make audio in anyone's voice from a script they didn't approve.
6. **Take**: `walkthrough/rig/takes/<name>.mjs`; run `--dry`, then for real. Fix dead air the recorder warns about.
7. **Film**: `walkthrough/films/<name>.film.json`, then `build_film.py ... --render`. If HyperFrames isn't in npm's cache yet, say it will download about 110 MB plus its headless Chrome (about 200 MB) and ask first.
8. **Check**: `check_film.py <work>/out/<name>.mp4`. Look at every contact sheet (cursor matches the words, nothing real or private on screen, captions don't hide the action). Use Earshot to check the sound if it's installed. Then **show the owner the MP4 and have them listen to it.**
9. **Publish**: only with the owner's OK, saying exactly what goes where, with a backout (how to unpublish the page and remove the file). Never overwrite an existing file without asking. Verify it signed out.
10. **Clean up**: reset demo data, stop the app, keep the script, take and film spec.

For "re-record <name>": same script and voice, a new take on the current app, rendered under the same file name.

Bulk files (frames, voice, recordings, films) go to the work folder or `~/Library/Caches`, never into the kit or an iCloud-synced folder. Passwords and keys are never written into kit files or printed.
