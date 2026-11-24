# Set up a brand

Say **"set up my brand"** (or "add a brand for <name>"). Claude interviews you, then writes `brands/<slug>/brand.json`, `BRAND.md` and `VOICE.md`, and shows you a preview card in the brand's colours and fonts before it's used on a video. You can run it once per brand: a business, a personal channel, a side project.

You can also skip the interview: copy `brands/example-brand/` to `brands/<your-brand>/` and edit the files.

## For Claude: how to run the interview

Ask in small groups (two or three questions at a time), offer choices where you can, and accept "skip" for anything. Never invent facts about the brand; leave a field empty or marked "ask me" instead. If the person has a brand guide, logo files, a website or a few past posts, ask for them first and fill in what you can from them, then confirm each value.

**1. The basics**
- What's it called, and what short name should the folder use (lowercase, dashes)?
- In one or two sentences: what does it make or sell, and who is it for?
- Handle or website to put on end cards?

**2. The look**
- Brand colours: hex codes if they have them, or a logo/website to read them from. Map them to the roles in `brand.json` (background, surface, text, accent, highlight, good, bad, dark). Ask which colour must never be a background.
- Fonts: names or files for titles, headings, captions and big numbers. Bought fonts go in `brands/<slug>/fonts/` (kept out of git). If they have none, offer three Mac system pairings from `lib/studio_config.py` (`SYSTEM_FONTS`) and show them.
- Logo: a PNG with a transparent background, for end cards.
- Footage feel: warm, neutral or cool? Bright and airy, or moody?

**3. On screen**
- What must never be on screen? (Other brands' packaging, screens with customer details, a competitor's sign, an old logo, prices that change.) → `keep_out`
- People: does everyone visible need to say yes first? Children allowed? Staff? Customers? → `people`
- Effects: lively, or restrained and quiet? Any favourites? → `effects`

**4. The voice** (writes `VOICE.md`)
- Three words for how it sounds.
- Words and phrases they always use, and ones they never want.
- Emojis, all-caps, exclamation marks: yes or no?
- Two or three captions or hooks from past posts they liked, as examples.
- How should videos usually end: a question, a call to visit, a follow ask, nothing?

**5. Videos**
- Typical length for reels? Long-form (YouTube) too?
- Which of the studio's styles fit (`STYLES.md`)? Offer a one-line description of each.
- Music: under everything, only under footage, or none under talking?

**Then:**
1. Write the three files. Use `brands/example-brand/` as the template and keep every key, even if empty.
2. Render a preview card: a 1080×1920 frame with a title, a caption on footage (or a plain panel), a tag and a big number, in the brand's colours and fonts (`.venv/bin/python styles/make_samples.py --footage <any clips> --out <scratch> --brand <slug>` if clips exist; otherwise a single frame from the Fast Cut engine). Show it and ask what to change.
3. Ask whether this should be the default brand (`default_brand` in `studio.json`).
4. Add one paragraph for the brand under "By brand" in `guides/storytelling.md` from the answers in part 5.

Brand facts never go in the house rules; they live in the brand's folder so each brand can differ.
