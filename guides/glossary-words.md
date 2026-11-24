# Glossary words

The Glossary page (`/studio/glossary`) builds itself from the effects, `STYLES.md` and this file. This file holds only the words that aren't defined anywhere else: the studio's own terms, the tracker's statuses, and names given to looks made for one video.

How a line is written, so the page can read it: `- **Name** (where it came from, if it's a look): one plain line. Status: in review. (the file it's from)`. The status is only for looks. When you approve a video with something new in it, its name goes under "Looks made for one video (in review)" (`guides/after-approval.md`), and comes off that list when you say it can be reused.

## Studio words

- **Style**: a named look you approved, with its own builder: Fast Cut, Talking Head Classic or Hands-On Classic. There's no default; Claude asks which. (STYLES.md)
- **Skin**: the colours and type a Fast Cut video wears: Dark, or Brand (from the brand's own colours and fonts). (STYLES.md)
- **Brand**: one folder in `brands/` with a brand's colours, fonts, logo, keep-out list, people rules and voice. Every builder and effect reads it. (brands/README.md)
- **House rules**: the standing rules Claude follows on every video, before any style or brand rule. (rules/README.md)
- **Style test**: a new look or version waiting for your OK, saved in the shoot's `Style Tests/` folder. (CLAUDE.md)
- **Older version**: an export that a newer version replaced, kept with its review notes in `Older Versions/`. (CLAUDE.md)
- **Effect**: a named visual effect that can go on any stretch of any video, each with its own slash command. (effects/README.md)
- **Effects pass**: the sound effects every new video and re-edit gets, only where something on screen causes them, and under the voice. (sound/README.md)
- **Sound map**: a small file beside a finished video that lets Video Review show its voice, music, footage sound and each sound effect on separate rows. (sound/README.md)
- **Effects map**: a small file beside a finished video that lets Video Review name what's on screen over each stretch. (effects/README.md)
- **Build record**: what a render shows over each stretch, the raw seconds it used and its separate sound tracks, kept by the builder; both maps are made from it. (library/README.md)
- **Beat**: one spoken line of a video in Video Review, its words lighting up as they're said. With no transcript, each shot is a beat. (review/README.md)
- **Note**: a comment you leave at an exact moment in Video Review, saved next to the video. It stays open until Claude fixes it, then shows done with Claude's reply. (review/README.md)
- **Log card**: the record of what's in one raw clip, moment by moment, saved next to the clip. (library/README.md)
- **Moment**: one stretch of a raw clip on its log card: what happens, what's said, its tags and flags. (library/README.md)
- **Copy ref**: the Footage tab button that copies a clip and its times, ready to paste to Claude or into a project card. (review/README.md)
- **Video tracker**: the list of every finished video, test and older version, with its status, posted date and link. (library/README.md)
- **Shoot folder**: one folder per shoot in your content folder, named by the first day filmed. (library/README.md)
- **Keep-out**: something that must never show in a cut, like another company's product, a private screen or a person who didn't agree. (brands/README.md)
- **Safe zones**: the edges of the frame that the app's buttons and captions cover. Nothing important goes there. (rules/house-rules.md)
- **CLAUDE-WROTE**: the mark on any text Claude wrote, like a title, a label or a joke, so you can OK it before posting. (rules/house-rules.md)
- **Project card**: the form that starts an edit on the Studio page: what it's for, the footage, the style. Saved in `cards/`. (cards/README.md)
- **Classroom**: reels you saved for how they're edited, broken down into what to take and what to leave. (classroom/README.md)
- **Ideas**: reels you saved for what they say, such as a strategy or a way to shoot. Kept apart from the Classroom, and never used as an editing reference. (ideas/README.md)
- **Storytelling guide**: your own rules for telling a story, each with where it came from. (guides/storytelling.md)

## Tracker statuses

- **in review**: waiting for you to watch it. New style tests start here. (library/footage.py)
- **ready to post**: finished and approved, not posted yet. Finished videos start here. (library/footage.py)
- **scheduled**: set to go out at a later time. (library/README.md)
- **posted**: live, with the date and the link. (library/README.md)
- **shelved**: kept, but not going to be posted, like an approved effect's preview or a test you won't use. (library/README.md)
- **superseded**: a newer version replaced it. Older versions start here. (library/footage.py)

## Looks made for one video (in review)

Nothing yet. When an edit makes a look worth naming, it's added here as one line, for example:
`- **Name** (the video it's from, YYYY-MM-DD): what it looks like, in one line. Status: in review. (where it's built)`
