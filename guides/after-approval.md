# When you approve a video

You approve a video with something like "approve this one" or "I'm about to post that one". Claude then does all of this in one go, without being asked. Steps 2 to 4 are how the studio gets a little smarter with every video.

1. **Finish the package.** Move the file from `Style Tests/` to the shoot's `Finished/Instagram Reels/` (or `Finished/YouTube/`) with its sound map and effects map (`<video>.sound.json`, `<video>.effects.json`) if it has them, using `library/finish.py`. Set it to "ready to post" in the video tracker, make the reel cover, and write `Instagram captions.txt` next to it (the caption in the brand's voice, from `brands/<brand>/VOICE.md`). Copy the video and cover to `~/Downloads`. Remind you of any on-screen text Claude wrote and of anyone recognisable.
2. **Name anything new.** List what was made for this edit that isn't in the Glossary yet: an effect, a look, a caption treatment, a layout. Suggest a short name for each and ask you to keep it or rename it. Then add it:
   - A new effect gets its `effects/catalog/<name>.py`, a preview and a slash command (`effects/README.md`, "Add an effect"), and its name goes on the in-review list in `effects/README.md` and `.claude/skills/effects/SKILL.md`.
   - Anything else gets one line in `guides/glossary-words.md`, under "Looks made for one video (in review)", with the video it came from.
   Either way it shows on the Glossary page as **in review**.
3. **Approving the video isn't approving the look.** A new thing stays in review until you say it can be reused ("use that again"). Then it comes off the in-review list. A look becomes a named style in `STYLES.md` only when you approve it as a style.
4. **Learn from the notes.** Read the notes on this video and its earlier versions (`<video>.notes.json`, including the ones in `Older Versions/`). A note that says how you like things in general goes into `guides/storytelling.md` under the right heading, with the video and the date, in your words where possible. A one-off fix doesn't. If a note clashes with a rule already there, Claude asks which one wins.
5. **Update the records.** Run `.venv/bin/python library/usage.py && .venv/bin/python library/footage.py index`. If the edit has a project card, set its status to "approved" (`cards/`).
6. **Tell you in two lines** what was named, what went into the guide, and what's still in review.
