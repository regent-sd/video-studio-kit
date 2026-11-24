# Start here

This folder is a **video studio** that Claude runs for you. You film, Claude edits, you review and approve. Your videos aren't kept in this folder: they live in your **content folder** (you pick it at setup; `~/Movies/Video Studio` by default).

## First time

Open Claude Code in this folder and say **"set up my studio"**. Claude will:

1. Check your Mac and install the tools, asking before each download.
2. Ask where your videos should live and write your settings (`studio.json`).
3. Show you the **house rules** and ask: adopt them, go through them one by one, or start clean.
4. Interview you about your **brand**: colours, fonts, logo, what must never be on screen, and how you sound.
5. Build a free starter **sound-effects library**.
6. Help you set up **VoiceStudio** if you want voiceovers in your own voice (you make the clone in the app; Claude uses it).
7. Download a few free **stock clips** and render a sample of every style and effect from them, so you can see what each looks like.

## The front door

Everything starts on the **Studio page**, which runs on your Mac only. Say **"open the studio"**. From there you can start a new edit, review a video, search your footage, see what's posted, and read the glossary, the classroom, the ideas and the guides.

## How a video gets made

1. **Film.** Make a shoot folder named by the day (`2026-03-14 Kitchen Remodel`) in your content folder and put the clips in its `Raw/` folders (`Raw/Camera`, `Raw/POV`, `Raw/Phone`…). Tell Claude **"log new footage"**.
2. **Start a card.** On the Studio page, **Start a new edit**: the title, brand, style, footage, what the video is for, and what to keep in or leave out.
3. **Plan.** Tell Claude **"start the card <name>"**. Claude reads the card, your rules and your brand and shows a plan. Nothing is built until you say go.
4. **Build.** Claude builds it in the style you picked and saves it to the shoot's `Style Tests/` folder.
5. **Review.** Open it in Video Review, pause where something should change, press **N** and type a note. Then tell Claude **"apply my notes on <video>"**. Each round makes a new version (v2, v3…).
6. **Approve.** **"Approve this one."** Claude moves it to `Finished/`, makes the cover and caption, marks it ready to post, names anything new it made, and adds what your notes taught it to your storytelling guide.
7. **Post**, then tell Claude **"mark <video> posted"**.

## Where things are

| | |
|---|---|
| `rules/house-rules.md` | Your standing rules |
| `guides/storytelling.md` | How you like a story told, learned from your notes |
| `guides/what-to-say.md` | Every phrase Claude knows |
| `brands/` | Your brands: colours, fonts, voice |
| `STYLES.md` | The named styles |
| `CLAUDE.md` | Claude's instructions |
| `setup/` | Installing, VoiceStudio, brand and sound guides, and `doctor.py` (checks everything) |

## Please don't

- Edit or rename anything in a shoot's `Raw/` folder. Those are the camera originals.
- Delete a `.notes.json` file. It holds your notes on that video.
- Overwrite a video someone left notes on. A fix is always a new version.
