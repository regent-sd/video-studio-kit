# Tagging the Asset Library

How every file in the Asset Library gets its description and tags. The tagging agents follow this page, and `tags.py` checks their work against it (it reads the word lists straight from here, so this page is the one source). The point of the tags: when you say "make a post about the spring launch" or "find a photo of the shop front", Claude (or you, on the search page) finds the right files fast, and knows which ones are safe to use.

The fixed lists below fit most small businesses. The last section, **Your business**, is yours: your own subjects, locations, how your brand looks now and how it used to look. Setup can fill it in by asking you a few questions (say **"set up my asset tags"**), or you can edit it by hand. Words are lower case with hyphens, in backticks.

## What you write, per file

One entry per unique file (per md5; every copy of the same file shares it):

```json
"<md5>": {
  "description": "Two people packing orders at a long wooden table, window light, shot from above.",
  "tags": {
    "type": "photo",
    "subject": ["staff-at-work", "packaging"],
    "setting": "on-site",
    "location": "main-location",
    "item": ["Gift Box"],
    "people": ["Sam"],
    "people_count": "few",
    "campaign": "Holiday 2025",
    "year": 2025,
    "use": "ready-to-post",
    "rating": 3
  },
  "flags": ["people-visible"],
  "brand_status": "current"
}
```

Leave a key out when it doesn't apply or you can't tell. A wrong tag is worse than a missing one.

## Description

One plain sentence, 25 words at most, saying what is literally in the picture: the thing, where, how it's shot. For a design file: what it is and what it says ("Tri-fold price list, 2021 prices, old round logo"). Use words a person would search for. No opinions, no guesses about who someone is.

## Tags (fixed lists; use these exact words)

**type** (one): `photo`, `logo`, `illustration`, `pattern`, `menu`, `label`, `packaging`, `signage`, `social-graphic`, `ad`, `print-piece`, `business-card`, `gift-card`, `template`, `document`, `screenshot`, `video`, `audio`, `cut-file` (laser or vinyl cutter files), `other`

**subject** (one to three, most important first):
- People: `staff-at-work`, `staff-portrait`, `team-group`, `owner`, `customers`, `hands-only`, `crowd`
- Places: `interior`, `exterior`, `storefront`, `workspace`, `counter`, `outdoor-area`, `vehicle`
- Things: `product`, `product-detail`, `product-group`, `packaging`, `merch`, `equipment`, `tools`, `materials`, `food`, `drink`, `animal`, `plant`
- Moments: `event`, `behind-the-scenes`, `process`, `delivery`, `before-after`
- Design content: `logo-mark`, `wordmark`, `menu-board`, `price-list`, `hours`, `map`, `icon`, `texture`, `infographic`, `chart`
- `other`
- Your own subjects are added from **Your business** below.

**setting** (one, photos and video only): `studio` (plain or styled backdrop), `flat-lay`, `on-site` (at your own business), `client-site`, `outdoors`, `event`, `home`, `online` (a screen or screenshot)

**location** (one; only when the folder path or something readable in the picture shows it): the words are listed under **Your business** below.

**item** (list, free text): the named product, service, menu item or offer, spelled as the folder, file name or a readable label gives it ("Gift Box", "Spring Tune-Up"). Don't invent names.

**people** (list of names): ONLY names that appear in the folder path or file name. Never name anyone from their face. **people_count**: `none`, `one`, `few` (2–4), `group` (5+).

**campaign** (free text, from the path): "Spring 2026", "Grand Opening", "10 Year Anniversary".

**year** (number): from the path or the photo's own date (`taken` in batch.json), else leave out.

**use** (one):
- `ready-to-post`: finished and clean; in a "Ready to Post" / "Final" folder, or plainly a final edit
- `raw`: straight from a camera, unedited, or one of many near-identical frames
- `print-ready`: final PDF or artwork made for a printer
- `source-file`: editable original (ai, psd, indd, fig)
- `web`: sized or made for the website
- `reference`: kept for the record (old versions, proofs, scans)

**rating** (1–3, photos and video only): `3` a hero shot worth posting as it is; `2` usable; `1` weak (blurry, dark, awkward, test shot).

## Flags (any that apply)

- `people-visible`: a recognisable person is in it (staff or anyone else). Get their OK before posting.
- `customers-visible`: recognisable customers or members of the public
- `kids-visible`: a child is in it. Keep children out of public posts unless a parent has said yes.
- `prices-shown`: prices are readable (they may be out of date)
- `dated-info`: shows a date, hours, an event or an offer that expires
- `old-logo`: a retired logo or look of yours is visible (see **Your business**)
- `other-brand`: another company's logo or product is prominent (a partner, a supplier, an equipment maker)
- `text-heavy`: mostly words
- `low-quality`: blurry, very dark, tiny or badly compressed
- `near-duplicate`: one of a run of almost identical frames (tag the best one `rating: 3` and the rest with this flag)
- `sensitive`: shows private information: a card or bank number, a signed form, a contract or invoice, staff records, someone's personal phone or address. The search page shows no preview for these, and they should not be in a marketing folder at all.

## brand_status (one)

- `current`: shows your brand as it looks today, or is a brand file made for the current look
- `retired`: shows an old logo or look, or lives in an archive folder of old brand material
- `neutral`: no branding visible (most photos of products, places and people)
- `unknown`: can't tell

## Rules

1. Tag what you can see plus what the folder path and file name tell you. Say nothing you can't support from those.
2. Never identify a person from their face. Names come only from folder paths and file names.
3. Use the path: a folder named for a place gives the location; `Menus/2021` gives the year; `Ready to Post` gives the use.
4. Every file in your batch gets an entry, including the ones with no preview (tag those from name, path and kind, and keep the description modest: "Illustrator source file for the 2022 price list").
5. Only the listed words for the fixed lists. If nothing fits, use `other` and say what it is in the description.
6. Before anything goes out in public, someone reads its flags. The tags are written from small previews and are right most of the time, not every time: look at the real file before it is posted.

## Your business (tailor this section)

Setup fills this in by asking you about your business; edit it any time. `tags.py vocab` shows the word lists as the checker reads them, so run it after an edit. Each bold field name below adds its words to that list above (a field name the lists above don't have adds a new tag). Replace the example words with your own.

**subject** (your own subjects, added to the list above):
- Your products or services: `signature-product`, `seasonal-product`, `custom-order`
- Your places and moments: `workshop`, `pop-up`, `class`

**location** (one): `main-location`, `second-location`, `warehouse`, `offsite`

### Your brand's looks

- **Current look:** describe today's logo and colours in a sentence, e.g. "round badge logo with the name in capitals, dark green and cream". Name the folder that holds the current logo files.
- **Retired looks:** describe each old logo or look, with the years it was used if you know them, and the folder that holds them. Anything showing one of these gets `brand_status: retired` and the `old-logo` flag.
- **Reference sheets:** `previews.py reference current "<folder of current logos>"` and `previews.py reference retired "<folder of old logos>"` make sheets the tagging agents compare against.

### Names, places and campaigns in your folders

- Folders named after people (staff portraits, an event with a named guest): the agents may copy those names into `people`, exactly as the folder spells them.
- Folders named after a place: say which location word each one maps to, e.g. "anything under Shop 2 is second-location".
- Campaign folders: the names to use for **campaign**, spelled as the folders spell them.
- Anything the agents should know about your files that isn't obvious from a picture.
