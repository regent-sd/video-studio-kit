"""Fit a music track you picked to a video's length, so it still ends on its own ending.

Usage: .venv/bin/python styles/stylekit/fit_music.py <out.wav> <seconds> <file>[@start] [<file>[@start] ...]
       .venv/bin/python styles/stylekit/fit_music.py --info <file>[@start] [seconds]   (tempo, first beat, lengths that fit)

  One file: the track plays from "start" (default 0; use it to skip a slow intro) and still ends on its own ending.
  To shorten it, one cut takes out a stretch of the middle where the music on both sides of the cut matches
  (same chords, same sound, same beat), lined up to the sample and crossfaded. When the tempo is clear the cut is a
  whole number of bars, so the phrase stays in place; time a montage to a length --info lists to end exactly on it.
  A track shorter than the video gets longer the same way, by jumping back to a matching earlier point.
  Several files (long videos): they play in order, each through to its natural end with a short breath between;
  only the last one is cut to fit.

Writes 48 kHz stereo 16-bit at about -11.5 LUFS, so a builder's music level means the same for every track.
Prints where it cut, so a bad cut can be moved by changing "start".
"""
import subprocess, sys
import numpy as np
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

SR = 48000
HOP = 1024                    # feature frame: ~21 ms
TARGET_LUFS = -11.5
GAP = 0.6                     # breath between tracks
XFADE = 0.25                  # crossfade at a cut
KEEP_HEAD, KEEP_TAIL = 4.0, 8.0   # never cut inside the first / last seconds of a track
EARLY, LATE = 1.0, 0.3        # the track may end this much before / after the video ends


def load(path, start=0.0):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).reshape(-1, 2).astype(float)
    # trim digital silence at both ends (keep the ring-out of the last chord)
    lvl = uniform_filter1d(np.abs(x).max(axis=1), 480)
    on = np.nonzero(lvl > 10 ** (-50 / 20))[0]
    tail = np.nonzero(lvl > 10 ** (-60 / 20))[0]
    if len(on) == 0:
        sys.exit(f"{path}: silent")
    return x[on[0] if start == 0 else 0: tail[-1] + 1]


def tempo(x):
    """(bpm, first beat in seconds, confidence 0-1) from the onset envelope; bpm is folded into 85-170."""
    H = 96                                           # 2 ms
    hp = np.diff(x.mean(axis=1), prepend=0)
    n = len(hp) // H
    e = np.log1p(1e3 * np.sqrt((hp[:n * H].reshape(n, H) ** 2).mean(axis=1)))
    on = np.maximum(np.diff(e, prepend=e[0]), 0)
    on = np.maximum(on - uniform_filter1d(on, 250), 0)
    fps = SR / H

    def ac(lag):
        lag = int(round(lag))
        return np.dot(on[:-lag], on[lag:]) / (len(on) - lag) if 0 < lag < len(on) // 2 else 0.0
    cands = np.arange(85.0, 170.0, 0.05)
    sc = np.array([ac(8 * 60 / b * fps) + ac(16 * 60 / b * fps) + ac(4 * 60 / b * fps) for b in cands])
    k = int(np.argmax(sc))
    bpm = float(cands[k])
    base = np.dot(on, on) / len(on)
    conf = float(min(1.0, sc[k] / (3 * base + 1e-12)))
    period = 60 / bpm * fps
    phases = np.arange(0, period, 0.5)
    score = [on[np.round(np.arange(p0, len(on) - 1, period)).astype(int)].sum() for p0 in phases]
    return bpm, float(phases[int(np.argmax(score))] / fps), conf


def features(x):
    """Per-frame chroma (harmony), 8 log bands (sound), onset strength (rhythm), level. Rows are frames."""
    mono = x.mean(axis=1)
    n_fft = 4096
    nfr = max(1, (len(mono) - n_fft) // HOP + 1)
    win = np.hanning(n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    pitch = np.where((freqs > 55) & (freqs < 4000), np.round(12 * np.log2(np.maximum(freqs, 1) / 440) + 69) % 12, -1)
    edges = np.geomspace(40, 16000, 9)
    band = np.digitize(freqs, edges) - 1
    chroma, bands, flux, level = [], [], [], []
    prev = None
    for c0 in range(0, nfr, 2048):
        idx = np.arange(c0, min(nfr, c0 + 2048))[:, None] * HOP + np.arange(n_fft)
        mag = np.abs(np.fft.rfft(mono[idx] * win, axis=1))
        p = mag ** 2
        chroma.append(np.stack([p[:, pitch == k].sum(axis=1) for k in range(12)], axis=1))
        bands.append(np.stack([p[:, band == k].sum(axis=1) for k in range(8)], axis=1))
        lm = np.log1p(mag)
        d = np.diff(np.vstack([lm[:1] if prev is None else prev, lm]), axis=0)
        flux.append(np.maximum(d, 0).sum(axis=1))
        prev = lm[-1:]
        level.append(10 * np.log10(p.sum(axis=1) + 1e-12))
    chroma = np.log1p(np.vstack(chroma) * 1e3)
    chroma /= np.linalg.norm(chroma, axis=1, keepdims=True) + 1e-9
    bands = np.log10(np.vstack(bands) + 1e-10)
    bands -= bands.mean(axis=1, keepdims=True)
    flux = np.concatenate(flux)
    flux /= np.percentile(flux, 95) + 1e-9
    level = np.concatenate(level)
    return np.hstack([chroma * 2.0, bands * 0.25, flux[:, None] * 0.8, (level[:, None] - level.max()) / 12])


def best_jump(F, r_lo, r_hi, i_lo, i_hi, w, bar=None):
    """Frame i and offset r (output = track[:i] + track[i + r:]) whose surroundings match best. With the bar length
    (frames) known, jumps of whole bars win: anything else is penalised, so the phrase stays in place after the cut."""
    best = (np.inf, None, None)
    for r in range(r_lo, r_hi + 1):
        if r == 0:
            continue
        pen = 0.0
        if bar:
            off = abs(abs(r) / bar - round(abs(r) / bar)) * bar      # frames from the nearest whole number of bars
            pen = 1.5 * min(1.0, (off / (bar / 8)) ** 2)
        a, b = (F[:-r], F[r:]) if r > 0 else (F[-r:], F[:r])
        d = uniform_filter1d(((a - b) ** 2).sum(axis=1), 2 * w + 1, mode="nearest")
        # index of d is the earlier of the two points; convert to the cut point i. Both the cut point and where it
        # lands (i + r) stay between the protected intro and ending.
        lo, hi = (i_lo, min(i_hi - r, len(d) - 1)) if r > 0 else (i_lo - r, min(i_hi, len(d) - 1 - r))
        if hi <= lo:
            continue
        seg = (d[lo:hi] if r > 0 else d[lo + r:hi + r]) + pen
        k = int(np.argmin(seg))
        if seg[k] < best[0]:
            best = (float(seg[k]), lo + k, r)
    return best


def refine(x, s, t):
    """Shift the destination t (samples) by up to one frame so the transients on both sides of the cut line up."""
    hp = np.abs(np.diff(x.mean(axis=1), prepend=0))
    env = uniform_filter1d(hp, 96)[::12]            # 4 kHz envelope
    s4, t4, half, lag = s // 12, t // 12, int(1.5 * 4000), HOP // 12
    if s4 - half < 0 or t4 - half - lag < 0 or s4 + half > len(env) or t4 + half + lag > len(env):
        return t
    ref = env[s4 - half:s4 + half]
    ref = ref - ref.mean()
    scores = [np.dot(ref, env[t4 - half + k:t4 + half + k] - env[t4 - half + k:t4 + half + k].mean())
              for k in range(-lag, lag + 1)]
    return t + (int(np.argmax(scores)) - lag) * 12


def splice(x, s, t):
    """x[:s] then x[t:], equal-power crossfade centred on the cut."""
    h = int(XFADE * SR / 2)
    if s - h < 0 or t + h > len(x) or t - h < 0:
        return np.vstack([x[:s], x[t:]])
    ramp = np.linspace(0, np.pi / 2, 2 * h)[:, None]
    mid = x[s - h:s + h] * np.cos(ramp) + x[t - h:t + h] * np.sin(ramp)
    return np.vstack([x[:s - h], mid, x[t + h:]])


def fit(x, need, name):
    """Cut or extend track x (samples) so it lasts need seconds, ending on its own ending."""
    w = int(3.0 * SR / HOP)
    bpm, _, conf = tempo(x)
    bar = 4 * 60 / bpm * SR / HOP if conf > 0.2 else None
    if need > 1.5 * len(x) / SR:
        print(f"  warning: {name} ({len(x) / SR:.0f}s) has to repeat to fill {need:.0f}s; "
              f"add another track so it doesn't loop")
    for _ in range(8):
        have = len(x) / SR
        diff = have - need          # > 0: too long, cut; < 0: too short, jump back
        if -EARLY <= diff <= LATE:
            return x
        F = features(x)
        nf = len(F)
        i_lo, i_hi = int(KEEP_HEAD * SR / HOP), nf - int(KEEP_TAIL * SR / HOP)
        if diff > 0:
            r_lo, r_hi = int((diff - LATE) * SR / HOP), int((diff + EARLY) * SR / HOP)
        else:
            body = (i_hi - i_lo) * HOP / SR
            add = min(-diff, 0.8 * body)
            r_lo, r_hi = -int((add + LATE) * SR / HOP), -int(max(add - EARLY, 0.5) * SR / HOP)
        if diff > 0 and i_hi - r_lo <= i_lo:
            sys.exit(f"{name}: too short to cut down to {need:.1f}s while keeping its intro and ending; "
                     f"lower its @start or pick a longer track")
        score, i, r = best_jump(F, r_lo, r_hi, i_lo, i_hi, w, bar)
        if i is None:
            sys.exit(f"{name}: no place to cut")
        s, t = i * HOP, refine(x, i * HOP, (i + r) * HOP)
        x = splice(x, s, t)
        bars = f", {abs(t - s) / SR / (bar * HOP / SR):.2f} bars" if bar else ""
        print(f"  {name}: {'cut' if r > 0 else 'repeat'} {abs(t - s) / SR:.2f}s at {s / SR:.1f}s{bars} "
              f"(match {score:.2f}, lower is better)")
    return x


def lufs(path):
    out = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float([ln for ln in out.splitlines() if ln.strip().startswith("I:")][-1].split()[1])


def main(out, seconds, items):
    total = float(seconds)
    tracks = []
    for it in items:
        path, _, st = it.rpartition("@") if "@" in it and it.rsplit("@", 1)[1].replace(".", "", 1).isdigit() else (it, "", "0")
        tracks.append((path, load(path, float(st or 0)), float(st or 0)))
    head = sum(len(x) / SR + GAP for _, x, _ in tracks[:-1])
    need = total - head
    if len(tracks) > 1 and need < 15:
        sys.exit(f"the earlier tracks already fill {head:.0f}s of {total:.0f}s; use fewer or shorter tracks")
    name = tracks[-1][0].rsplit("/", 1)[-1]
    x_last = tracks[-1][1]
    if need < KEEP_HEAD + KEEP_TAIL + 3 and len(x_last) / SR > need:
        # a very short video: the track's own ending, faded in (there's no room to cut the middle)
        last = x_last[-int(round(need * SR)):].copy()
        f = min(len(last) // 3, int(0.6 * SR))
        last[:f] *= np.linspace(0, 1, f)[:, None]
        print(f"  {name}: short video, so its last {need:.1f}s, faded in")
    else:
        last = fit(x_last, need, name)
    parts = []
    for k, (_, x, st) in enumerate(tracks[:-1] + [(None, last, tracks[-1][2])]):
        if st > 0:                                  # started mid-track: fade in
            f = int(0.5 * SR)
            x = x.copy()
            x[:f] *= np.linspace(0, 1, f)[:, None]
        parts.append(x)
        if k < len(tracks) - 1:
            parts.append(np.zeros((int(GAP * SR), 2)))
    mix = np.vstack(parts)
    n = int(round(total * SR))
    if len(mix) > n:                                # ran a little long: fade the last moment
        mix = mix[:n]
        f = int(LATE * SR)
        mix[-f:] *= np.linspace(1, 0, f)[:, None]
    else:
        mix = np.vstack([mix, np.zeros((n - len(mix), 2))])
    tmp = out + ".tmp.wav"
    wavfile.write(tmp, SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))
    gain = 10 ** ((TARGET_LUFS - lufs(tmp)) / 20)
    mix *= gain
    peak = np.abs(mix).max()
    if peak > 0.95:                                 # quieter tracks pushed up: soft-limit the peaks
        mix = np.tanh(mix / 0.95) * 0.95
    wavfile.write(out, SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))
    import os
    os.unlink(tmp)
    print(f"wrote {out}: {total:.1f}s from {len(tracks)} track(s), gain {20 * np.log10(gain):+.1f} dB")


def info(item, near=None):
    """Tempo, where the first beat falls once the leading silence is trimmed, and the video lengths the track fits
    with a cut of whole bars (so a montage can be timed to end exactly with the music)."""
    path, _, st = item.rpartition("@") if "@" in item and item.rsplit("@", 1)[1].replace(".", "", 1).isdigit() else (item, "", "0")
    x = load(path, float(st or 0))
    bpm, first, conf = tempo(x)
    bar = 4 * 60 / bpm
    L = len(x) / SR
    print(f"{path.rsplit('/', 1)[-1]}: {L:.2f}s, {bpm:.2f} BPM (confidence {conf:.2f}), beat {60 / bpm:.4f}s, "
          f"first beat at {first:.3f}s")
    fits = [L - n * bar for n in range(0, int(L / bar)) if L - n * bar >= 15]
    if near:
        fits = sorted(fits, key=lambda v: abs(v - near))[:4]
    print("lengths that fit with a cut of whole bars:", ", ".join(f"{v:.2f}s" for v in sorted(fits)))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--info":
        info(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else None)
        sys.exit()
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
