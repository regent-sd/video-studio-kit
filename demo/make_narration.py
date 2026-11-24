#!/usr/bin/env python3
"""Make the demo narration: speech from demo/narration.md, its word times, and a talking take with sound.

    .venv/bin/python demo/make_narration.py
    .venv/bin/python demo/make_narration.py --voice "Daniel" --rate 170
    .venv/bin/python demo/make_narration.py --engine voicestudio     # your VoiceStudio voice (studio.json voice.profile_id)

It writes, in the demo shoot (the newest '<date> Demo Shoot' in your content folder, or --shoot):
  Raw/Camera/voiceover.wav             the narration, 48 kHz mono
  Raw/Camera/voiceover.wav.words.txt   when each word is said ('start-end word' per line, seconds)
  Raw/Camera/talking-head.mp4          the talking take with the narration as its sound (the stock clip has
                                       none), plus talking-head.mp4.words.txt. The clip as downloaded moves
                                       to .stock/ in the shoot, and every run starts from that copy.

Options:
  --shoot DIR        the shoot folder (default: the newest demo shoot; made for today if there's none)
  --script FILE      the script (default demo/narration.md: the lines under '## Script')
  --engine auto|say|voicestudio   auto (default) uses VoiceStudio when studio.json has voice.profile_id,
                     else macOS say. If VoiceStudio isn't running, auto falls back to say.
  --voice NAME       the macOS voice (say -v '?' lists them). Default: the first installed of a few clear ones.
  --rate N           words per minute for say (default 190)
  --no-voice-clip    don't add the narration to the talking take
  --no-transcribe    skip the word times (whisper-cli)

Needs: ffmpeg and whisper-cli (setup installs them) with the model ~/.cache/whisper.cpp/ggml-base.en.bin
(or set "whisper_model" in studio.json).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_common as dc  # noqa: E402

sc = dc.sc
PREFERRED_VOICES = ["Reed (English (US))", "Eddy (English (US))", "Daniel", "Samantha", "Alex", "Fred"]
DEFAULT_MODEL = "~/.cache/whisper.cpp/ggml-base.en.bin"


def say_(*a):
    print(*a, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit(f"{Path(cmd[0]).name} failed:\n{(r.stderr or r.stdout).strip()[-1500:]}")
    return r


# ------------------------------------------------------------------ speech
def mac_voices() -> dict[str, str]:
    """Installed macOS voices: {name: locale}."""
    r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    out = {}
    for line in r.stdout.splitlines():
        m = re.match(r"^(.*?)\s+([a-z]{2}_[A-Z]{2})\b\s*#", line)
        if m:
            out[m.group(1).strip()] = m.group(2)
    return out


def speak_mac(lines: list[str], dest: Path, voice: str | None, rate: int) -> str:
    if not dc.tool("say"):
        raise SystemExit("macOS 'say' isn't here. Use --engine voicestudio, or run this on a Mac.")
    have = mac_voices()
    if voice and voice not in have:
        english = [n for n, loc in have.items() if loc.startswith("en_")]
        raise SystemExit(f"No macOS voice called '{voice}'. English voices here include: {', '.join(english[:15])}")
    if not voice:
        voice = next((v for v in PREFERRED_VOICES if v in have), None)
    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(tmp) / "script.txt"
        txt.write_text("\n".join(lines) + "\n")
        cmd = ["say", "-r", str(rate), "-f", str(txt), "-o", str(dest),
               "--file-format=WAVE", "--data-format=LEI16@48000"]
        if voice:
            cmd[1:1] = ["-v", voice]
        run(cmd)
    return f"macOS say ({voice or 'system voice'}, {rate} wpm)"


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    body = b"".join(
        f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in fields.items()
    ) + f"--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def speak_voicestudio(lines: list[str], dest: Path, v: dict) -> str:
    api = (v.get("api") or "http://127.0.0.1:3900").rstrip("/")
    pid = v.get("profile_id")
    if not pid:
        raise RuntimeError("studio.json has no voice.profile_id (setup/VOICE-STUDIO.md)")
    fields = {"text": "\n".join(lines), "profile_id": pid}
    if v.get("seed"):
        fields["seed"] = str(v["seed"])
    body, ctype = multipart(fields)
    req = urllib.request.Request(f"{api}/generate", data=body, method="POST", headers={"Content-Type": ctype})
    say_(f"Asking VoiceStudio at {api} (the first call can take a minute while the model loads)...")
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            data, rtype = r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"VoiceStudio said HTTP {e.code}: {e.read()[:300]!r}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"can't reach VoiceStudio at {api} ({getattr(e, 'reason', e)}). Is the app open?")
    if not data.startswith(b"RIFF"):
        raise RuntimeError(f"VoiceStudio didn't send a WAV ({rtype}): {data[:200]!r}")
    dest.write_bytes(data)
    return f"VoiceStudio ({v.get('name') or 'profile ' + pid[:8]})"


def finish_audio(raw: Path, dest: Path):
    """48 kHz mono, a quarter second of room at the start, half a second at the end, a steady level."""
    if not dc.tool("ffmpeg"):
        shutil.copyfile(raw, dest)
        return
    run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
         "adelay=250:all=1,apad=pad_dur=0.5,loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(dest)])


# ------------------------------------------------------------------ word times
def transcribe(wav: Path, model: Path) -> list[tuple[float, float, str]]:
    if not dc.tool("whisper-cli"):
        raise SystemExit("whisper-cli isn't installed (setup installs it: brew install whisper-cpp). Or use --no-transcribe.")
    if not model.exists():
        raise SystemExit(f"No whisper model at {model}. Setup downloads it; or set 'whisper_model' in studio.json.")
    with tempfile.TemporaryDirectory() as tmp:
        w16, out = Path(tmp) / "a16.wav", Path(tmp) / "out"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(w16)])
        run(["whisper-cli", "-m", str(model), "-f", str(w16), "-l", "en", "-dtw", "base.en", "-nfa", "-ojf",
             "-of", str(out), "-np"])
        d = json.loads(Path(str(out) + ".json").read_text(errors="replace"))
    # Same reading as the Footage Log's transcripts: a word starts at its DTW time and lasts until the
    # next word starts (or its line ends); sound tags like "[music]" or "(laughs)" are dropped.
    words: list[list] = []
    for seg in d.get("transcription", []):
        seg_end = seg["offsets"]["to"] / 1000
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if text.startswith("[") or not text.strip():
                continue
            s = tok.get("t_dtw", -1) / 100
            if s < 0:
                s = tok["offsets"]["from"] / 1000
            if text.startswith(" ") or not words:
                words.append([s, seg_end, text.strip()])
            else:
                words[-1][2] += text
    words = [w for w in words if not re.fullmatch(r"[\(\[].*[\)\]]", w[2])]
    for a, b in zip(words, words[1:]):
        if b[0] > a[0]:
            a[1] = min(a[1], b[0])
    return [(round(a, 2), round(max(b, a + 0.05), 2), w) for a, b, w in words]


def match_score(lines: list[str], words: list[tuple[float, float, str]]) -> float:
    norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())  # noqa: E731
    said = [norm(w) for _, _, w in words]
    want = [norm(w) for w in " ".join(lines).split()]
    hits, j = 0, 0
    for w in want:
        k = j
        while k < len(said) and k < j + 4 and said[k] != w:
            k += 1
        if k < len(said) and said[k] == w:
            hits, j = hits + 1, k + 1
    return hits / max(1, len(want))


# ------------------------------------------------------------------ the talking take
def voice_clip(shoot: Path, clip: dict, wav: Path, words) -> str:
    raw = dc.clip_path(shoot, clip)
    stock = dc.stock_path(shoot, clip)
    if not stock.exists():
        if not raw.exists():
            return f"skipped {clip['id']}: not downloaded yet (run demo/fetch_stock.py)"
        info = dc.probe(raw)
        if info.get("has_audio"):
            return f"skipped {clip['id']}: {raw.name} already has sound, so it isn't the stock clip; left as it is"
        stock.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(raw), str(stock))
    vid, aud = dc.probe(stock).get("duration", 0), dc.probe(wav).get("duration", 0)
    tmp = raw.with_name(raw.stem + ".voicing.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(stock), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
         "-movflags", "+faststart", str(tmp)])
    tmp.replace(raw)
    if words:
        dc.write_words(raw, [w for w in words if w[0] < vid] if vid else words)
    note = f" (the narration runs {aud:.1f} s, the clip {vid:.1f} s: the end is cut)" if vid and aud > vid else ""
    return f"{clip['camera']}/{raw.name}: the talking take with the narration as its sound{note}"


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description="Make the demo narration and its word times.")
    ap.add_argument("--shoot")
    ap.add_argument("--script", default=str(dc.SCRIPT_FILE))
    ap.add_argument("--engine", choices=["auto", "say", "voicestudio"], default="auto")
    ap.add_argument("--voice")
    ap.add_argument("--rate", type=int, default=190)
    ap.add_argument("--no-voice-clip", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true")
    a = ap.parse_args()

    lines = dc.read_script(Path(a.script).expanduser())
    shoot = dc.shoot_dir(a.shoot, create=True)
    cam = shoot / "Raw" / "Camera"
    cam.mkdir(parents=True, exist_ok=True)
    out = cam / "voiceover.wav"
    say_(f"Demo shoot: {shoot}")
    say_(f"Script: {len(lines)} lines, {len(' '.join(lines).split())} words")

    v = sc.voice()
    engine = a.engine
    if engine == "auto":
        engine = "voicestudio" if v.get("profile_id") else "say"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "speech.wav"
        if engine == "voicestudio":
            try:
                how = speak_voicestudio(lines, raw, v)
            except RuntimeError as e:
                if a.engine == "voicestudio":
                    raise SystemExit(f"VoiceStudio: {e}")
                say_(f"VoiceStudio: {e}\nUsing macOS say instead.")
                how = speak_mac(lines, raw, a.voice, a.rate)
        else:
            how = speak_mac(lines, raw, a.voice, a.rate)
        finish_audio(raw, out)
    dur = dc.probe(out).get("duration", 0)
    say_(f"Wrote Raw/Camera/{out.name}: {dur:.1f} s, {how}")

    words = []
    if not a.no_transcribe:
        model = Path(sc.get("whisper_model") or DEFAULT_MODEL).expanduser()
        say_("Transcribing with whisper.cpp for word times...")
        words = transcribe(out, model)
        wp = dc.write_words(out, words)
        score = match_score(lines, words)
        say_(f"Wrote Raw/Camera/{wp.name}: {len(words)} words, {score:.0%} match the script"
             + ("" if score >= 0.85 else " (low: listen to it, or try another --voice)"))

    if not a.no_voice_clip:
        for clip in dc.load_clips()["clips"]:
            if clip.get("voice"):
                say_(voice_clip(shoot, clip, out, words))

    say_("\nNext: .venv/bin/python demo/run_samples.py   (renders the style samples and effect previews)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
