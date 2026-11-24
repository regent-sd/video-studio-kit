"""Transcripts, captions and cut points.

A clip's transcript sits next to it as <clip>.words.txt, one word per line: "251.04-251.62 shaky" (seconds).
The Footage Log makes these when footage is logged; words_for() makes one if it's missing (whisper-cli with
DTW word times, which land within about 0.1 s; plain Whisper word times can drift by a second).

Cut points come from the sound, not the transcript: a cut ends at the first real pause after the last word
(or the quietest moment before the next word) and starts where the sound begins after the silence before the first
word. That is what keeps words from being clipped. Always check a voice edit by ear or with a re-transcription
(talking-head/verify.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import media, paths

STOP = set("""a an the and or but so um uh like just really very that this these those then than there their they them
i me my we our you your he she it its is are was were be been being to of in on at for with as by from up out about into
over after before again more most some such no not only own same too can will just don't do does did have has had what
which who whom when where why how all any both each few other here also get got gonna going im i'm it's that's yeah okay ok""".split())
FILLERS = {"um", "uh", "erm", "hmm", "mm"}


def model_path() -> str:
    return os.path.expanduser(paths.sc.get("whisper_model") or "~/.cache/whisper.cpp/ggml-base.en.bin")


def read_words(path) -> list[dict]:
    """[{"s", "e", "w"}] from a .words.txt file (lines "a-b word"; bracketed noise tags are skipped)."""
    out = []
    for ln in open(path, errors="replace"):
        m = re.match(r"\s*([\d.]+)-\s*([\d.]+)\s+(.*)", ln)
        if not m or not m[3].strip() or m[3].startswith("[") or m[3].startswith("("):
            continue
        out.append(dict(s=float(m[1]), e=float(m[2]), w=m[3].strip()))
    return out


def write_words(path, ws):
    with open(path, "w") as fh:
        fh.writelines(f"{w['s']:.2f}-{w['e']:.2f} {w['w']}\n" for w in ws)


def transcribe(clip, out=None) -> Path:
    """Word-level transcript of a clip with whisper-cli. Writes <clip>.words.txt (or `out`); returns its path."""
    clip = Path(clip)
    out = Path(out) if out else Path(str(clip) + ".words.txt")
    if not media.probe(clip)["has_audio"]:
        out.write_text("")
        return out
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        media.ff(["-i", clip, "-vn", "-ac", 1, "-ar", 16000, "-c:a", "pcm_s16le", wav])
        r = subprocess.run(["whisper-cli", "-m", model_path(), "-f", str(wav), "-l", "en", "-dtw", "base.en", "-nfa",
                            "-ojf", "-of", str(Path(tmp) / "out"), "-np"], capture_output=True, text=True)
        js = Path(tmp) / "out.json"
        if r.returncode != 0 or not js.exists():
            raise RuntimeError(f"whisper-cli failed on {clip.name}: {(r.stderr or r.stdout).strip()[-300:]}")
        d = json.loads(js.read_text(errors="replace"))
    words = []
    for seg in d.get("transcription", []):
        seg_end = seg["offsets"]["to"] / 1000
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if text.startswith("[") or text.startswith(" [") or not text.strip():
                continue
            t = tok.get("t_dtw", -1) / 100
            if t < 0:
                t = tok["offsets"]["from"] / 1000
            if text.startswith(" ") or not words:
                words.append([t, seg_end, text.strip()])
            else:
                words[-1][2] += text
    for i in range(len(words) - 1):   # a word ends where the next begins (capped at its segment's end)
        if words[i + 1][0] > words[i][0]:
            words[i][1] = min(words[i][1], words[i + 1][0])
    rows = [dict(s=a, e=max(b, a + 0.05), w=w) for a, b, w in words if not re.fullmatch(r"[\W_]+", w)]
    write_words(out, rows)
    return out


def words_for(clip, make=True) -> list[dict]:
    """The clip's words in its own time. Uses <clip>.words.txt; if it's missing, makes one (next to the clip, or
    in the cache when that folder can't be written)."""
    clip = Path(clip)
    beside = Path(str(clip) + ".words.txt")
    cached = paths.cache_dir() / "words" / (media.key(str(clip.resolve()), clip.stat().st_size) + ".words.txt")
    for p in (beside, cached):
        if p.exists():
            return read_words(p)
    if not make:
        return []
    try:
        p = transcribe(clip, beside)
    except OSError:   # the clip's folder is read-only
        cached.parent.mkdir(parents=True, exist_ok=True)
        p = transcribe(clip, cached)
    return read_words(p)


def clean(ws, drop_fillers=True) -> list[dict]:
    """Drop fillers (um, uh), join split words ("-ish"), mark words that end a phrase (brk)."""
    res = []
    for w in ws:
        t = w["w"]
        if drop_fillers and t.lower().strip(",.?!") in FILLERS:
            continue
        if t.startswith("-") and res:
            res[-1]["w"] += t
            res[-1]["e"] = w["e"]
            continue
        res.append(dict(w))
    for w in res:
        if w["w"][-1:] in ".,?!;:":
            w["brk"] = True
    return res


def chunk(ws, maxw=3, maxc=16, gap=0.35, max_word=0.7):
    """Caption chunks of 1-3 words. A new caption starts at punctuation, at a pause over `gap`, or when it would
    pass maxw words / maxc characters. Each word is capped at max_word seconds first (Whisper sometimes stretches
    a word across a pause). Returns [[word dicts]]."""
    ws = [dict(w, e=min(w["e"], w["s"] + max_word)) for w in ws]
    out, cur = [], []
    for w in ws:
        if cur:
            txt = " ".join(x["w"] for x in cur + [w])
            if (len(cur) >= maxw or len(txt) > maxc or w["s"] - cur[-1]["e"] > gap
                    or cur[-1]["w"][-1:] in ".,?!;:" or cur[-1].get("brk")):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def captions(ws, keywords=(), maxw=3, maxc=16, linger=0.45, max_len=1.6):
    """Timed captions from words: [(start, end, [(word, is_keyword)])]. A caption shows from just before its
    first word until just before the next caption (at most max_len seconds). Keywords: words in `keywords`
    (lower case) and any word with a digit. Punctuation at the ends is dropped."""
    keys = {k.lower() for k in keywords}
    groups = chunk(ws, maxw, maxc)
    caps = []
    for i, g in enumerate(groups):
        s = max(0.0, g[0]["s"] - 0.06)
        e = min(g[-1]["e"] + linger, s + max_len)
        if i + 1 < len(groups):
            e = min(e, groups[i + 1][0]["s"] - 0.06)
        toks = []
        for x in g:
            raw = x["w"].strip(",.;:")
            bare = raw.lower().strip("?!\"'")
            toks.append((raw, bare in keys or any(c.isdigit() for c in raw)))
        caps.append((s, max(e, s + 0.3), toks))
    return caps


def keywords_from(ws, n=8) -> list[str]:
    """Words worth highlighting when none are given: the longest content words (6+ letters, not common words),
    plus every word with a digit. A start, not a rule: for a real video, pick them from what's said."""
    seen, out = set(), []
    cands = sorted({re.sub(r"[^\w'-]", "", w["w"]).lower() for w in ws}, key=lambda x: (-len(x), x))
    for c in cands:
        if any(ch.isdigit() for ch in c):
            out.append(c)
        elif len(c) >= 6 and c not in STOP and c not in seen and len([o for o in out if not any(ch.isdigit() for ch in o)]) < n:
            out.append(c)
        seen.add(c)
    return out


def placeholder_words(t0, t1, text="placeholder caption words for this sample") -> list[dict]:
    """Made-up words spread over t0..t1, for samples of footage with no speech. Never for a real video."""
    toks = text.split()
    out, t, k = [], t0 + 0.2, 0
    while t < t1 - 0.3:
        out.append(dict(s=t, e=t + 0.32, w=toks[k % len(toks)]))
        t += 0.38 if (k % 3) != 2 else 0.7
        k += 1
    return out


# ---------------------------------------------------------------- cut points from the sound
_env: dict = {}


def level(clip):
    """10 ms RMS level of a clip's sound (16 kHz mono), cached: (env array, index -> seconds is i / 100)."""
    k = str(clip)
    if k not in _env:
        x = media.read_audio(clip, 0, media.probe(clip)["duration"] or 0.01, sr=16000, ramp=0)
        hop = 160
        n = len(x) // hop
        x = x[: n * hop].reshape(n, hop) if n else np.zeros((1, hop), np.float32)
        _env[k] = np.sqrt((x.astype(np.float64) ** 2).mean(axis=1))
    return _env[k]


def pause_level(clip, ws) -> float:
    """The level below which this clip counts as a pause: a quarter of the way from the room's noise floor to
    the voice's typical level (set from the clip, so a quiet lav and a loud room both work)."""
    env = level(clip)
    if not len(env):
        return 0.0
    inside = np.zeros(len(env), bool)
    for w in ws:
        inside[int(w["s"] * 100):int(w["e"] * 100) + 1] = True
    speech = float(np.median(env[inside[:len(env)]])) if inside.any() else float(np.percentile(env, 70))
    floor = float(np.percentile(env, 8))
    return floor + 0.25 * max(0.0, speech - floor)


def quiet_runs(env, thr, t0, t1, min_len):
    """(start, end) of stretches in t0..t1 where the level stays under thr for at least min_len seconds."""
    runs, start = [], None
    i0, i1 = max(0, int(t0 * 100)), min(int(t1 * 100), len(env))
    for i in range(i0, i1 + 1):
        q = i < i1 and env[i] < thr
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) / 100 >= min_len:
                runs.append((start / 100, i / 100))
            start = None
    return runs


def quietest(env, lo, hi):
    a, b = max(0, int(lo * 100)), max(int(lo * 100) + 1, int(hi * 100))
    b = min(b, len(env))
    if b <= a:
        return lo
    return (a + int(np.argmin(env[a:b]))) / 100.0


def cut_points(clip, ws, i0, i1):
    """Sound-safe (start, end) seconds for the words ws[i0]..ws[i1] of a clip: never inside a word."""
    env = level(clip)
    thr = pause_level(clip, ws)
    w0, w1 = ws[i0], ws[i1]
    prev_e = ws[i0 - 1]["e"] if i0 else 0.0
    nxt_s = ws[i1 + 1]["s"] if i1 + 1 < len(ws) else min(w1["e"] + 0.8, len(env) / 100)
    lo = max(prev_e + 0.05, w0["s"] - 0.45)
    pre = quiet_runs(env, thr, lo, w0["s"] + 0.05, 0.05)
    a = pre[-1][1] - 0.03 if pre else quietest(env, max(prev_e + 0.05, w0["s"] - 0.18), w0["s"] - 0.005)
    hi = nxt_s - 0.015
    after = quiet_runs(env, thr, w1["s"] + 0.10, hi, 0.25)
    b = after[0][0] + 0.08 if after else quietest(env, max(w1["s"] + 0.10, hi - 0.28), hi)
    return round(max(0.0, a), 3), round(max(b, a + 0.1), 3)


def find(ws, text, after=0.0) -> int:
    """Index of the first word at or after `after` seconds where `text` (one or more words) starts."""
    want = [re.sub(r"[^\w']", "", t.lower()) for t in text.split()]
    norm = [re.sub(r"[^\w']", "", w["w"].lower()) for w in ws]
    for i in range(len(ws)):
        if ws[i]["s"] + 1e-6 < after:
            continue
        if norm[i:i + len(want)] == want:
            return i
    # the transcript may have misheard a word: take the closest match, if it's close
    import difflib
    best, bi = 0.0, None
    for i in range(len(ws)):
        if ws[i]["s"] + 1e-6 < after:
            continue
        r = difflib.SequenceMatcher(None, " ".join(want), " ".join(norm[i:i + len(want)])).ratio()
        if r > best:
            best, bi = r, i
    if bi is not None and best >= 0.72:
        print(f"  note: '{text}' matched what the transcript heard: '{' '.join(w['w'] for w in ws[bi:bi + len(want)])}'")
        return bi
    raise KeyError(f"'{text}' isn't said after {after:.2f} s (check the transcript, <clip>.words.txt)")


def sentences(ws, max_gap=0.6):
    """Index ranges [(i0, i1)] of phrases: split at sentence ends and at pauses longer than max_gap."""
    out, s = [], 0
    for i, w in enumerate(ws):
        last = i == len(ws) - 1
        if last or w["w"][-1:] in ".?!" or ws[i + 1]["s"] - w["e"] > max_gap:
            out.append((s, i))
            s = i + 1
    return out


SAME = {"alright": "all right", "thru": "through", "ok": "okay", "gonna": "going to", "wanna": "want to"}


def norm_words(text) -> list[str]:
    """Lower-case words for comparing transcripts (spellings that sound the same are made the same)."""
    out = []
    for w in re.sub(r"[^a-z0-9' ]", " ", text.lower().replace("-", " ")).split():
        out += SAME.get(w, w).split()
    return out
