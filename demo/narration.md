# Demo narration

A short, neutral script for the demo shoot, so the styles and effects have speech to work with: captions, voice cuts and effects that land on a word. `make_narration.py` reads the lines under **Script**, one sentence per line, turns them into speech (macOS `say`, or your VoiceStudio voice if `studio.json` has a `voice.profile_id`), and transcribes the result with whisper.cpp for word times.

It's written to match the demo clips. Claude wrote it, so treat any of it that ends up on screen as Claude's wording, not yours. Change it freely and run `make_narration.py` again; the clips aren't touched.

## Script

Here's how we make a mug, start to finish.
The day starts early, with a quick workout and a walk to the studio.
First, we knead the clay by hand to push the air out.
Then it goes on the wheel. Slow hands, steady speed.
Once it's firm, we carve the details.
The glaze goes on in one smooth pour.
After the kiln, every cup gets checked on the shelf.
Orders come in on the laptop, and they ship the same day.
The best part? Tea from a mug you made yourself.
Go make something with your hands this week.

## Shot list

Which clip each line was written for (ids from `clips.json`). A demo edit can follow it in order.

| Line | Clips |
|---|---|
| Here's how we make a mug, start to finish. | `talking-head` |
| The day starts early, with a quick workout and a walk to the studio. | `town-aerial`, `workout`, `pov-walk` |
| First, we knead the clay by hand to push the air out. | `hands-kneading` |
| Then it goes on the wheel. Slow hands, steady speed. | `hands-wheel` |
| Once it's firm, we carve the details. | `hands-carving` |
| The glaze goes on in one smooth pour. | `glaze-pour` |
| After the kiln, every cup gets checked on the shelf. | `shelves`, `cups-detail` |
| Orders come in on the laptop, and they ship the same day. | `laptop-typing`, `phone-scroll` |
| The best part? Tea from a mug you made yourself. | `tea-pour` |
| Go make something with your hands this week. | `talking-head`, `talking-head-green` |
