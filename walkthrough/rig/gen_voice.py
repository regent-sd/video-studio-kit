#!/usr/bin/env python3
"""Make the narration for a walkthrough script, one clip per line.

    .venv/bin/python walkthrough/rig/gen_voice.py walkthrough/scripts/example.md            # your clone (VoiceStudio)
    .venv/bin/python walkthrough/rig/gen_voice.py walkthrough/scripts/example.md --say      # a Mac voice, before you have a clone
    ... --only 2,4          redo just scenes 2 and 4 (the rest of the manifest is kept)
    ... --name example      the voice folder's name (default: the script's file name)
    ... --mode line|scene   line: one call per line. scene: one call per scene, cut at the pauses
    ... --seed 42           keep a delivery you liked
    ... --ref-audio clip.wav --ref-text "exact words"   copy the energy of a livelier clip of you
    ... --clean             clean the room sound out of a --ref-audio take

Reads "## N. Title" scenes and their "- line" narration lines ("[screen]" lines are ignored).
"say: Written = Spoken" lines before the first scene change how a word is sent to the voice.
Writes <work>/voice/<name>/: s01_l01.wav ... (one per line, 48 kHz mono), scene_01.wav (each
scene's lines joined, for listening) and manifest.json (each line's text, file and length),
which the take and build_film.py read.

Every line is transcribed back (VoiceStudio's speech-to-text, or whisper.cpp) and compared with
the script; lines marked CHECK came out wrong: reword them or redo with another --seed.

Voice settings come from studio.json "voice": api, profile_id, engine (default voxcpm2), seed.
Only make audio from a script the owner approved, and have a person listen before it's used.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import studio_config as sc  # noqa: E402

GAP_S = 0.45            # pause between lines in the scene_NN.wav listening file
HEAD_S, TAIL_S = 0.15, 0.35
MATCH_OK = 0.85
SPLIT_OK = 0.6      # below this a scene's cut landed in the wrong pause


# ---------- script ----------

def parse(md: Path):
    scenes, cur, say = [], None, {}
    for raw in md.read_text(encoding="utf8").splitlines():
        line = raw.rstrip()
        m = re.match(r"^##\s+(\d+)\.\s+(.*)$", line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "lines": []}
            scenes.append(cur)
            continue
        m = re.match(r"^say:\s*(.+?)\s*=\s*(.+?)\s*$", line, re.I)
        if m and cur is None:
            say[m.group(1)] = m.group(2)
        elif cur and line.startswith("- "):
            cur["lines"].append(line[2:].strip())
    return scenes, say


def spoken(text: str, say: dict) -> str:
    for written, sound in say.items():
        text = re.sub(rf"(?<!\w){re.escape(written)}(?!\w)", sound, text)
    return text


def norm(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


# ---------- audio helpers ----------

def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def wav_seconds(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def to_wav(src: Path, dst: Path, extra_filter: str = ""):
    af = "aresample=48000,aformat=channel_layouts=mono" + (f",{extra_filter}" if extra_filter else "")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", af, "-c:a", "pcm_s16le", str(dst)])


def join(parts: list[Path], out: Path):
    """Join clips with short pauses into one listening file (not used in the film)."""
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in parts:
        args += ["-i", str(p)]
    chain = [f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,apad=pad_dur={GAP_S if i < len(parts) - 1 else TAIL_S}[a{i}]"
             for i in range(len(parts))]
    filt = ";".join(chain) + ";" + "".join(f"[a{i}]" for i in range(len(parts))) + \
        f"concat=n={len(parts)}:v=0:a=1,adelay={int(HEAD_S * 1000)}[out]"
    run(args + ["-filter_complex", filt, "-map", "[out]", "-c:a", "pcm_s16le", str(out)])


def silences(p: Path, noise_db=-38, min_s=0.16):
    """[(start, end)] of the quiet stretches in a file."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", f"silencedetect=noise={noise_db}dB:d={min_s}",
                        "-f", "null", "-"], capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:
        out.append((start, wav_seconds(p)))
    return out


def split_scene(take: Path, texts: list[str], outs: list[Path]) -> bool:
    """Cut one scene take into one clip per line, at the pauses nearest where each line
    should end (judged by its share of the scene's letters, long pauses preferred)."""
    total = wav_seconds(take)
    sil = silences(take)
    lead = sil[0][1] if sil and sil[0][0] <= 0.02 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= total - 0.02 else total
    inner = [s for s in sil if s[0] > lead + 0.05 and s[1] < tail - 0.05]
    n = len(texts)
    if len(inner) < n - 1:
        return False
    chars = [len(t) for t in texts]
    speech = tail - lead
    cuts, after = [], lead
    for k in range(1, n):
        expect = lead + speech * sum(chars[:k]) / sum(chars)
        left = n - 1 - k  # pauses still needed after this one
        options = [s for s in inner if s[0] > after]
        options = options[: len(options) - left] if left else options
        if not options:
            return False
        best = min(options, key=lambda s: abs((s[0] + s[1]) / 2 - expect) - 1.5 * (s[1] - s[0]))
        cuts.append(best)
        after = best[1]
    bounds = [max(0.0, lead - 0.06)] + [x for s in cuts for x in (s[0], s[1])] + [min(total, tail + 0.15)]
    for i, out in enumerate(outs):
        a = bounds[2 * i] if i == 0 else max(0.0, bounds[2 * i] - 0.06)
        b = bounds[2 * i + 1] + (0.12 if i < len(outs) - 1 else 0)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(take), "-af",
             f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,afade=t=out:st={max(0, b - a - 0.03):.3f}:d=0.03",
             "-c:a", "pcm_s16le", str(out)])
    return True


# ---------- voices ----------

class VoiceStudio:
    def __init__(self, a):
        v = sc.voice()
        self.api = (a.api or v.get("api") or "http://127.0.0.1:3900").rstrip("/")
        self.profile = a.profile or v.get("profile_id") or ""
        self.engine = v.get("engine", "voxcpm2")
        self.seed = a.seed if a.seed is not None else v.get("seed")
        self.speed = a.speed
        self.ref_audio, self.ref_text, self.clean = a.ref_audio, a.ref_text, a.clean
        if not self.ref_audio and not self.profile:
            sys.exit("No voice profile. Put your clone's id in studio.json \"voice.profile_id\" (setup/VOICE-STUDIO.md), "
                     "pass --profile, or use --say for a stand-in voice.")
        if not up(self.api):
            sys.exit(f"VoiceStudio isn't answering at {self.api}. Open the VoiceStudio app (its server runs while it's open), "
                     "or use --say for a stand-in voice.")
        self.name = "VoiceStudio " + (f"ref {Path(self.ref_audio).name}" if self.ref_audio else f"profile {self.profile}")

    def make(self, text: str, out: Path):
        args = ["curl", "-sf", "-m", "900", "-X", "POST", f"{self.api}/generate", "-F", f"text={text}", "-F", "language=en"]
        if self.ref_audio:
            args += ["-F", f"ref_audio=@{self.ref_audio}", "-F", f"ref_text={self.ref_text}"]
        else:
            args += ["-F", f"profile_id={self.profile}"]
        if self.engine:
            args += ["-F", f"engine={self.engine}"]
        if self.seed is not None:
            args += ["-F", f"seed={self.seed}"]
        if self.speed is not None:
            args += ["-F", f"speed={self.speed}"]
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.wav"
            run(args + ["-o", str(raw)])
            if self.clean:
                cleaned = Path(tmp) / "clean.wav"
                r = subprocess.run(["curl", "-sf", "-m", "600", "-X", "POST", f"{self.api}/clean-audio",
                                    "-F", f"audio=@{raw}", "-o", str(cleaned)])
                if r.returncode == 0 and cleaned.exists() and cleaned.read_bytes()[:4] == b"RIFF":
                    raw = cleaned
                else:
                    print("  note: /clean-audio didn't return audio; kept the take as made")
            to_wav(raw, out, "afftdn=nr=10:nf=-55:tn=1" if self.clean else "")


class MacSay:
    """macOS `say`: a stand-in so everything works before you have a clone. Not for posting."""

    def __init__(self, a):
        if not shutil.which("say"):
            sys.exit("--say needs macOS `say`.")
        self.voice, self.rate = a.say_voice, a.say_rate
        self.name = f"macOS say{f' ({self.voice})' if self.voice else ''}"

    def make(self, text: str, out: Path):
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "say.aiff"
            args = ["say", "-o", str(aiff)]
            if self.voice:
                args += ["-v", self.voice]
            if self.rate:
                args += ["-r", str(self.rate)]
            run(args + ["--", text.replace("\n", " [[slnc 450]] ")])
            to_wav(aiff, out)


def up(api: str) -> bool:
    return subprocess.run(["curl", "-sf", "-m", "3", f"{api}/health"], capture_output=True).returncode == 0


# ---------- checking ----------

class Checker:
    """Transcribes a clip with VoiceStudio's speech-to-text if it's open, else whisper.cpp."""

    def __init__(self, api: str):
        self.api = api if up(api) else None
        self.model = Path(sc.get("whisper_model") or "~/.cache/whisper.cpp/ggml-base.en.bin").expanduser()
        self.whisper = bool(shutil.which("whisper-cli")) and self.model.is_file()
        self.name = "VoiceStudio" if self.api else ("whisper.cpp" if self.whisper else None)

    def heard(self, p: Path) -> str | None:
        if self.api:
            r = subprocess.run(["curl", "-sf", "-m", "300", "-X", "POST", f"{self.api}/v1/audio/transcriptions",
                                "-F", f"file=@{p}", "-F", "model=whisper-1", "-F", "language=en"], capture_output=True, text=True)
            try:
                return json.loads(r.stdout).get("text", "").strip()
            except ValueError:
                return None
        if self.whisper:
            with tempfile.TemporaryDirectory() as tmp:
                w16 = Path(tmp) / "a.wav"
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(w16)])
                r = subprocess.run(["whisper-cli", "-m", str(self.model), "-f", str(w16), "-l", "en", "-nt", "-np"],
                                   capture_output=True, text=True)
                return " ".join(x.strip() for x in r.stdout.splitlines() if x.strip() and not x.strip().startswith("[")).strip()
        return None


def score(text: str, heard: str | None, say: dict) -> float | None:
    if not heard:
        return None
    want = norm(spoken(text, say))
    alt = norm(text)
    got = norm(heard)
    return round(max(difflib.SequenceMatcher(None, want, got).ratio(), difflib.SequenceMatcher(None, alt, got).ratio()), 2)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("script", type=Path)
    ap.add_argument("--name", help="voice folder name (default: the script's file name)")
    ap.add_argument("--out", type=Path, help="voice folder (default: <work>/voice/<name>)")
    ap.add_argument("--only", default="", help="scenes to (re)make, e.g. 2,4")
    ap.add_argument("--mode", choices=["line", "scene"], help="line (default for --say) or scene (default for VoiceStudio)")
    ap.add_argument("--say", action="store_true", help="use a macOS voice instead of your clone")
    ap.add_argument("--say-voice", default="", help="macOS voice for --say (see `say -v '?'`)")
    ap.add_argument("--say-rate", type=int, default=0, help="words per minute for --say")
    ap.add_argument("--api"); ap.add_argument("--profile")
    ap.add_argument("--seed", type=int); ap.add_argument("--speed", type=float)
    ap.add_argument("--ref-audio"); ap.add_argument("--ref-text", default="")
    ap.add_argument("--clean", action="store_true", help="clean the room sound out of a --ref-audio take")
    ap.add_argument("--no-check", action="store_true", help="skip transcribing each line back")
    a = ap.parse_args()
    if a.ref_audio and not a.ref_text:
        sys.exit("--ref-audio needs --ref-text: the exact words said in that clip.")

    wt = sc.get("walkthrough") or {}
    work = Path(wt.get("work_dir") or "~/Movies/Walkthroughs").expanduser()
    name = a.name or a.script.stem
    out = a.out or work / "voice" / name
    out.mkdir(parents=True, exist_ok=True)

    voice = MacSay(a) if a.say else VoiceStudio(a)
    mode = a.mode or ("line" if a.say else "scene")
    checker = None if a.no_check else Checker((a.api or sc.voice().get("api") or "http://127.0.0.1:3900").rstrip("/"))
    print(f"voice: {voice.name}; mode: {mode}; checking with: {checker.name if checker and checker.name else 'nothing (not checked)'}")

    scenes, say = parse(a.script)
    if not scenes:
        sys.exit(f"No scenes in {a.script}. Scenes start with '## 1. Title' and lines with '- '.")
    only = {int(x) for x in a.only.split(",") if x.strip()}
    mpath = out / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() and only else {"scenes": {}}
    manifest.update({"script": a.script.name, "engine": "say" if a.say else "voicestudio", "profile": voice.name, "mode": mode})

    flagged = []
    for s in scenes:
        if only and s["n"] not in only:
            continue
        files = [out / f"s{s['n']:02d}_l{i:02d}.wav" for i in range(1, len(s["lines"]) + 1)]
        checking = bool(checker and checker.name)
        heard = {}
        did_scene = False
        if mode == "scene" and len(s["lines"]) > 1:
            take = out / f"scene_{s['n']:02d}.take.wav"
            voice.make("\n".join(spoken(t, say) for t in s["lines"]), take)
            did_scene = split_scene(take, s["lines"], files)
            if did_scene and checking:
                heard = {f: checker.heard(f) for f in files}
                if any((score(t, heard[f], say) or 0) < SPLIT_OK for t, f in zip(s["lines"], files)):
                    did_scene, heard = False, {}
                    print(f"  scene {s['n']}: the cut between lines landed in the wrong pause; making it line by line")
            elif not did_scene:
                print(f"  scene {s['n']}: couldn't find a pause between every line; making it line by line")
        if not did_scene:
            for text, f in zip(s["lines"], files):
                voice.make(spoken(text, say), f)
        lines = []
        for i, (text, f) in enumerate(zip(s["lines"], files), 1):
            h = heard.get(f) if f in heard else (checker.heard(f) if checking else None)
            m = score(text, h, say)
            heard_text = h
            lines.append({"text": text, "file": f.name, "seconds": round(wav_seconds(f), 2), "heard": heard_text, "match": m})
            flag = "  <-- CHECK" if m is not None and m < MATCH_OK else ""
            if flag:
                flagged.append(f"{s['n']}.{i}")
            print(f"  s{s['n']:02d} l{i:02d} {lines[-1]['seconds']:5.2f}s match={m}{flag}  {text}")
        scene_wav = out / f"scene_{s['n']:02d}.wav"
        join(files, scene_wav)
        manifest["scenes"][str(s["n"])] = {"title": s["title"], "file": scene_wav.name,
                                           "seconds": round(wav_seconds(scene_wav), 2), "lines": lines}
        print(f"scene {s['n']} '{s['title']}': {manifest['scenes'][str(s['n'])]['seconds']}s")
        mpath.write_text(json.dumps(manifest, indent=2))

    total = sum(sc_["seconds"] for sc_ in manifest["scenes"].values())
    print(f"wrote {mpath}\ntotal narration: {total:.1f}s")
    if flagged:
        print(f"lines to check: {', '.join(flagged)} (reword them, or redo those scenes with --only and another --seed)")
    if a.say:
        print("note: this is a stand-in Mac voice for timing and drafts. Re-make it with your clone before posting.")


if __name__ == "__main__":
    main()
