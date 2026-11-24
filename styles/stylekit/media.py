"""ffmpeg helpers shared by the builders: probe a clip, crop it to a vertical frame, cut graded footage pieces
(cached), grab stills, read frames in order, read sound, and find where the person is in a frame.

Every piece is a whole number of frames (n) at 30 fps, so long edits never drift out of sync.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from . import paths

W, H, FPS, SR = 1080, 1920, 30, 48000
ENC = ["-an", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-pix_fmt", "yuv420p"]

# Colour looks. "punchy" is the Dark skin and Talking Head look; warm / neutral / cool are a brand's "grade"
# (brand.json) and the Hands-On look: bright and airy, mids lifted, highlights kept.
_LIFT = "eq=gamma=1.12:contrast=1.03:saturation=1.06,curves=master='0/0.03 0.25/0.30 0.5/0.57 0.75/0.82 1/1'"
LOOKS = {
    "punchy": "eq=contrast=1.08:saturation=1.14:gamma=1.03,unsharp=5:5:0.5",
    "punchy_pov": "eq=contrast=1.05:saturation=1.06,unsharp=5:5:0.3",
    "warm": f"colortemperature=temperature=5400:mix=0.25:pl=1,vibrance=intensity=0.18,{_LIFT}",
    "neutral": f"vibrance=intensity=0.15,{_LIFT}",
    "cool": f"colortemperature=temperature=7200:mix=0.2:pl=1,vibrance=intensity=0.12,{_LIFT}",
    "none": "null",
}
# Evens out exposure before a brand look (cameras differ; this brings them together).
_LEVEL = "normalize=blackpt=black:whitept=white:smoothing=30:independence=0:strength=0.3"
# Bright window behind the subject: same look, highlights roll off instead of clipping.
WINDOW = "curves=master='0/0 0.6/0.6 0.85/0.8 1/0.9'"
# A soft key light for a face the camera left dark, blended in through a feathered ellipse (face_mask()).
FACE_LIFT = "eq=gamma=1.28:contrast=1.06:saturation=1.05,curves=master='0/0.03 0.25/0.33 0.5/0.60 0.75/0.82 1/1'"


def grade(look: str = "punchy", pov: bool = False, window: bool = False) -> str:
    """The ffmpeg filter for a look. pov=True: a head-mounted or glasses camera (softer sharpening)."""
    look = look or "none"
    if look == "punchy":
        return LOOKS["punchy_pov" if pov else "punchy"]
    if look in ("warm", "neutral", "cool"):
        return f"{_LEVEL},{LOOKS[look]}" + (f",{WINDOW}" if window else "")
    return LOOKS.get(look, look)   # a raw ffmpeg filter string also works


def ff(args, quiet=True):
    subprocess.run(["ffmpeg", "-v", "error" if quiet else "info", "-y", "-nostdin"] + [str(a) for a in args], check=True)


def even(x) -> int:
    return int(round(x / 2.0)) * 2


def clamp(v, a, b):
    return max(a, min(b, v))


def key(*a) -> str:
    return hashlib.md5(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()[:16]


_probe: dict = {}


def probe(p) -> dict:
    """w, h (as shown, after any rotation), duration, fps, has_audio."""
    p = str(p)
    if p not in _probe:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation:stream_tags=rotate:format=duration",
                            "-of", "json", p], capture_output=True, text=True)
        d = json.loads(r.stdout or "{}")
        v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            rot = int(float(sd.get("rotation", 0) or 0))
        rot = rot or int(float((v.get("tags") or {}).get("rotate", 0) or 0))
        if abs(rot) % 180 == 90:
            w, h = h, w
        num, _, den = (v.get("r_frame_rate") or "30/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 30.0
        _probe[p] = dict(w=w, h=h, duration=float((d.get("format") or {}).get("duration", 0) or 0), fps=fps,
                         has_audio=any(s.get("codec_type") == "audio" for s in d.get("streams", [])))
    return _probe[p]


def probe_wh(p):
    d = probe(p)
    return d["w"], d["h"]


def crop_box(src, cx=None, cy=None, aspect=W / H, zoom=1.0):
    """(x, y, w, h) in source pixels: the biggest box of this aspect, zoomed, centred on (cx, cy) and kept inside."""
    sw, sh = probe_wh(src)
    cx = sw / 2 if cx is None else cx
    cy = sh / 2 if cy is None else cy
    h = sh / zoom
    w = h * aspect
    if w > sw / zoom:
        w = sw / zoom
        h = w / aspect
    w, h = min(even(w), even(sw)), min(even(h), even(sh))
    x = int(clamp(cx - w / 2, 0, sw - w))
    y = int(clamp(cy - h / 2, 0, sh - h))
    return (x, y, w, h)


def footage(src, t, n, box, size, look="punchy", pov=False, extra="", style="shared"):
    """n frames of src from t seconds, cropped to box, scaled to size, graded: a cached silent mp4.
    Returns (path, n, size) for Reader."""
    p = paths.cache_dir(style) / (key("ftg2", str(src), round(t, 3), n, box, size, look, pov, extra) + ".mp4")
    if not p.exists():
        g = grade(look, pov)
        vf = (f"crop={box[2]}:{box[3]}:{box[0]}:{box[1]},scale={size[0]}:{size[1]}:flags=lanczos,{g}"
              f"{(',' + extra) if extra else ''},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p")
        tmp = str(p) + ".tmp.mp4"
        ff(["-ss", f"{max(0.0, t):.3f}", "-t", f"{n / FPS + 1:.3f}", "-i", src, "-map", "0:v:0", "-vf", vf,
            "-frames:v", n] + ENC + [tmp])
        # a clip that ends early: hold its last frame so the piece is still n frames
        got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                  "stream=nb_read_frames", "-of", "csv=p=0", tmp], capture_output=True, text=True).stdout.strip() or 0)
        if got < n:
            ff(["-i", tmp, "-vf", f"tpad=stop_mode=clone:stop={n - got}", "-frames:v", n] + ENC + [tmp + ".pad.mp4"])
            os.replace(tmp + ".pad.mp4", tmp)
        os.replace(tmp, p)
    return (str(p), n, tuple(size))


def still(src, t, box=None, size=(W, H), look="punchy", pov=False, style="shared") -> Image.Image:
    """One graded frame of src at t, cropped and scaled (cached PNG). An image file works too."""
    if Path(src).suffix.lower() in paths.IMAGE_EXT:
        im = Image.open(src).convert("RGB")
        if box:
            im = im.crop((box[0], box[1], box[0] + box[2], box[1] + box[3]))
        return im.resize(size, Image.LANCZOS)
    box = box or crop_box(src, aspect=size[0] / size[1])
    p = paths.cache_dir(style) / (key("still2", str(src), round(t, 3), box, size, look, pov) + ".png")
    if not p.exists():
        ff(["-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", 1, "-vf",
            f"crop={box[2]}:{box[3]}:{box[0]}:{box[1]},scale={size[0]}:{size[1]}:flags=lanczos,{grade(look, pov)}", p])
    return Image.open(p).convert("RGB")


def raw_frame(src, t, max_w=640) -> Image.Image:
    """An ungraded frame, scaled down (for finding the subject)."""
    p = paths.cache_dir() / (key("raw1", str(src), round(t, 2), max_w) + ".png")
    if not p.exists():
        ff(["-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", 1, "-vf", f"scale='min({max_w},iw)':-2", p])
    return Image.open(p).convert("RGB")


class Reader:
    """Frames of one layer, read in order: get(i) is frame i of the scene. parts: [(mp4, n, size)]."""

    def __init__(self, parts):
        self.parts, self.pi, self.proc, self.left, self.pos, self.last = parts, -1, None, 0, -1, None
        self.size = parts[0][2] if parts else (W, H)

    def _next_part(self):
        self.close()
        self.pi += 1
        if self.pi >= len(self.parts):
            return False
        p, n, self.size = self.parts[self.pi]
        self.left = n
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return True

    def _read(self):
        while self.left <= 0:
            if not self._next_part():
                return
        n = self.size[0] * self.size[1] * 3
        b = self.proc.stdout.read(n)
        if len(b) == n:
            self.last = Image.frombytes("RGB", self.size, b)
        self.left -= 1

    def get(self, i):
        while self.pos < i:
            self._read()
            self.pos += 1
        return self.last if self.last is not None else Image.new("RGB", self.size, (0, 0, 0))

    def close(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
            self.proc = None


def read_audio(path, a, b, sr=SR, ramp=0.012) -> np.ndarray:
    """Mono float32 sound of path from a to b seconds (silence if the clip has no sound), with tiny fades."""
    want = int(round((b - a) * sr))
    if not probe(path)["has_audio"]:
        return np.zeros(want, np.float32)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(path), "-map", "0:a:0",
                          "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).copy()
    x = np.pad(x, (0, max(0, want - len(x))))[:want]
    f = min(int(ramp * sr), len(x) // 4)
    if f > 0:
        r = np.linspace(0, 1, f, dtype=np.float32)
        x[:f] *= r
        x[-f:] *= r[::-1]
    return x


# ---------------------------------------------------------------- where the person is
SWIFT_MASK = paths.STYLES / "person_mask.swift"


def person_mask(im: Image.Image, tag: str) -> Image.Image | None:
    """Greyscale person mask for an image (Apple Vision through person_mask.swift), cached. None if no person."""
    d = paths.cache_dir() / "masks"
    d.mkdir(exist_ok=True)
    src, out = d / f"{tag}.png", d / f"{tag}_mask.png"
    if not out.exists():
        im.convert("RGB").save(src)
        r = subprocess.run(["swift", str(SWIFT_MASK), str(src), str(out)], capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            return None
    return Image.open(out).convert("L").resize(im.size)


def subject(src, t=None) -> dict:
    """Where the person is in a clip, in source pixels: cx (the head's centre), the highest the head goes (top),
    the body's centre (cy) and whether one was found. Looks at three frames (a fifth, half and four fifths of the
    way in) with Apple Vision, so one crop holds for the whole clip; cached. With no person (hands, a product,
    a screen), the frame centre. t is accepted for older callers and ignored."""
    sw, sh = probe_wh(src)
    dur = probe(src)["duration"] or 1.0
    cf = paths.cache_dir() / "subjects.json"
    try:
        known = json.loads(cf.read_text())
    except (OSError, ValueError):
        known = {}
    k = key("subj2", str(src), round(dur, 2), sw, sh)
    if k in known:
        return known[k]
    res = dict(cx=sw / 2, cy=sh / 2, top=sh * 0.15, found=False)
    tops, cxs, cys = [], [], []
    for f in (0.2, 0.5, 0.8):
        try:
            fr = raw_frame(src, dur * f)
            m = person_mask(fr, f"{k}_{int(f * 10)}")
            if m is None:
                continue
            a = np.asarray(m, np.float32) / 255.0
            if a.mean() < 0.01:
                continue
            ys, xs = np.nonzero(a > 0.5)
            if not len(xs):
                continue
            s = sw / fr.width
            head = ys < np.percentile(ys, 25)   # the top quarter decides cx (shoulders and arms pull the centroid)
            tops.append(float(np.percentile(ys, 1)) * s)
            cxs.append(float(xs[head].mean()) * s)
            cys.append(float(ys.mean()) * s)
        except Exception:
            continue
    if tops:
        res = dict(cx=float(np.median(cxs)), cy=float(np.median(cys)), top=float(min(tops)), found=True)
    known[k] = res
    try:
        cf.write_text(json.dumps(known))
    except OSError:
        pass
    return res


def frame_for(src, kind="full", zoom=None, t=None, at=None, room=None):
    """A crop box for a clip in one of the layouts: full (1080x1920), half (1080x960, the bottom of a split screen),
    punch (full, tighter). Follows the person when there is one; at=(cx, cy, zoom) sets it by hand. room: the
    space above the head as a share of the frame (default 8%, 11% when zoomed in)."""
    size = (W, H) if kind in ("full", "punch") else (W, 960)
    aspect = size[0] / size[1]
    if at:
        cx, cy, z = at
        return crop_box(src, cx, cy, aspect, z), size
    sw, sh = probe_wh(src)
    s = subject(src, t)
    z = zoom or {"full": 1.0, "half": 1.35, "punch": 1.3}[kind]
    if not s["found"]:
        return crop_box(src, sw / 2, sh / 2, aspect, z), size
    ch = min(sh, sh / z)
    if aspect * ch > sw:
        ch = sw / aspect
    # a little room above the head: 8% of the frame (10% when tighter)
    room = room if room is not None else (0.08 if z <= 1.05 else 0.11)
    cy = s["top"] - room * ch + ch / 2
    return crop_box(src, s["cx"], cy, aspect, z), size
