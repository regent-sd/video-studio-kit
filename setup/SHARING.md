# Sharing the kit

How to hand the kit to someone else, or keep your own changed copy in sync, without your footage, voice or private details going with it.

## What never leaves your Mac

`.gitignore` keeps these out of git, and the leak check (below) blocks them even if someone forces them in:

- `studio.json` (your paths, name and voice id)
- all video, audio, photos and `.ovsvoice` voice files
- work folders, caches, previews, node_modules, the `.venv`
- your brands (only `brands/example-brand/` is tracked; add your own to git only if you mean to share it)
- bought fonts (`brands/*/fonts/`)
- `.env` files and any keys

## The leak check

`scripts/leak_check.py` runs before every commit (install the hook once with `python3 scripts/leak_check.py --install-hook`). It blocks:

- words on your private list, `~/.config/video-studio-kit/leak-terms.txt`: your name, family, staff, brands, products, partners, places. The list lives outside the repo, so the repo never names what it's hiding. One term per line.
- home-folder paths, cloud-drive mount paths, email addresses and links to individual social posts
- media files and anything over 1 MB

Run it by hand any time: `python3 scripts/leak_check.py`.

## Private GitHub repo (recommended)

1. Make a GitHub account for the kit if you don't want your personal or business account's name on it.
2. Create a **private** repository, then from the kit folder:
   ```bash
   git remote add origin https://github.com/<account>/<repo>.git
   git push -u origin main
   ```
3. Invite people: repository **Settings → Collaborators → Add people**. They clone it, open Claude Code in it, and say "set up my studio".
4. Send updates by committing and pushing; they get them with `git pull`. Their `studio.json`, brands, rules and content stay theirs, because those files are either ignored or only made at setup.

For someone who doesn't use git: on GitHub, **Releases → Draft a new release**, and they download the zip it makes. A zip in a shared drive folder works too, but they won't get updates.

## Before you share it more widely

- Run the leak check and read `git log -p` once for anything personal in old commits. A public repo can't be taken back once it's been cloned.
- Decide the license (`LICENSE.md`). The placeholder says "shared privately, don't redistribute".
- Check the third-party licenses (`setup/INSTALL.md`), especially Remotion's for companies, and the stock sites' terms (`demo/README.md`).
