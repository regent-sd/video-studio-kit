# Project cards

Every edit can start as a card. You fill it in on the Studio page (**Start a new edit**, `/studio/new`), and it's saved here as `<date>-<title>.card.json`, for example `2026-03-14-kitchen-remodel-the-reveal.card.json`. The page lists them under **Edits**, and opens each one for editing.

This folder starts empty. Your cards are yours: keep them out of a shared copy of the kit unless you mean to share them.

## What's on a card

| Field | What it is |
|---|---|
| `title` | The edit's name |
| `brand`, `brand_other` | The brand's folder name in `brands/` (for example `example-brand`), or `Other` with its name in `brand_other` |
| `style` | One of the styles in `STYLES.md` (Fast Cut once per skin: `Fast Cut – Dark skin`, `Fast Cut – Brand skin`; `Talking Head Classic`; `Hands-On Classic`), or `Ask me`. A card saved with no style says "Ask me": there's no default style |
| `shoots`, `clips` | The shoot folders, and clip refs pasted from the Footage tab's **Copy ref**, one per line |
| `vision` | What the video is for and how it should feel |
| `script` | The script or talking points |
| `length`, `platform` | How long, and where it goes |
| `must_keep`, `must_avoid` | Lines, shots or facts that stay in; people, logos, screens or lines that stay out |
| `classroom`, `effects`, `references` | Classroom cards and effects you want, and anything else |
| `status` | new, in progress, in review, approved |
| `created`, `updated` | When it was made and last saved |

## "start the card <name>" (for Claude)

1. Find the card: match the name to a card's `title` or file name. If two match, ask which.
2. Read the card, `rules/house-rules.md`, `guides/storytelling.md`, the brand's folder (`brands/<brand>/`: `brand.json`, `BRAND.md`, `VOICE.md`), the style in `STYLES.md` (if the style is "Ask me", ask which one first, with a line on each), the Glossary (`/studio/glossary`, or `effects/README.md` and `.claude/skills/effects/SKILL.md`), and any classroom cards it names.
3. Look at the footage it points to (the Footage Log, the clips' log cards and transcripts).
4. Propose a plan before building: the story in order, the footage with times, each effect with its moment and why it fits, any text Claude would write (flagged), the music question, and anything on the card you can't do. Wait for the go.
5. Build it the usual way (the style's builder, the sound-effects pass in `sound/README.md`, `library/finish.py`), and set the card's `status` to "in progress", then "in review" once it's in Video Review.

## Editing a card by hand

Claude may edit a card file directly (for example to set `status`). Keep the other fields as they are, and set `updated` to the current time (`2026-03-14T09:30:00`). If the card is open on the Studio page, the next save there says it changed and asks to reload, instead of overwriting the change. Extra fields Claude adds (a plan file, output paths) are kept when the card is saved from the page.
