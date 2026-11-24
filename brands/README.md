# Brands

One folder per brand you make videos for. Each holds:

| File | What it is |
|---|---|
| `brand.json` | Colours, fonts, logo, keep-out list, people rules, effect and music settings. Every builder and effect reads it. |
| `BRAND.md` | The brand guide in words: who it is, how it looks, what never goes on screen. |
| `VOICE.md` | How the brand sounds: captions, hooks and anything Claude writes. |
| `logo.png` | Optional. A transparent PNG for end cards. |
| `fonts/` | Optional. Font files the brand uses (kept out of git). |

`example-brand/` is a made-up brand so everything works on day one. To add your own, tell Claude **"set up my brand"** (`setup/BRAND-SETUP.md` has the interview), or copy `example-brand/` and edit it. Set `default_brand` in `studio.json` to the one you use most.
