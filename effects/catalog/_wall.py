"""Helpers shared by couch-wall, headline-wall, cover-story, glass-type and doodle-boil.
(The leading underscore keeps this file out of the effects list.)"""
import re, datetime, subprocess
import numpy as np
from PIL import Image, ImageFilter
from core import W, H, norm_word

FILLERS = {"um", "uh", "uhm", "umm", "er", "ah", "so", "and", "but", "like"}


# ------------------------------------------------------------------ homographies (flat planes in perspective)
def homog(src, dst):
    """3x3 matrix taking the 4 points src to the 4 points dst."""
    A, B = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(B, float))
    return np.append(h, 1.0).reshape(3, 3)

def apply_h(M, pts):
    p = np.c_[np.asarray(pts, float), np.ones(len(pts))] @ M.T
    return p[:, :2] / p[:, 2:3]

def pil_coeffs(M):
    """PIL PERSPECTIVE data for a transform whose output pixel (x, y) reads input M @ (x, y, 1)."""
    M = M / M[2, 2]
    return tuple(M.ravel()[:8])


# ------------------------------------------------------------------ loops of this video (for tiles that play)
_LOOPS = {}
def loops(subj, starts, n, size):
    """Frames [s, s + n) for each start s, scaled to size (w, h): uint8 array (len(starts), n, h, w, 3).
    One ffmpeg pass, cached per process."""
    key = (subj.dir, tuple(starts), n, tuple(size))
    if key in _LOOPS: return _LOOPS[key]
    w, h = size
    want = sorted({min(subj.n - 1, s + j) for s in starts for j in range(n)})
    expr = "+".join(f"between(n,{a},{b})" for a, b in _runs(want))
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", subj.base, "-vf", f"select='{expr}',scale={w}:{h}:flags=area",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    raw = p.stdout
    fs = w * h * 3
    got = {}
    for k, i in enumerate(want):
        b = raw[k * fs:(k + 1) * fs]
        if len(b) == fs: got[i] = np.frombuffer(b, np.uint8).reshape(h, w, 3)
    blank = np.full((h, w, 3), 40, np.uint8)
    out = np.stack([np.stack([got.get(min(subj.n - 1, s + j), blank) for j in range(n)]) for s in starts])
    _LOOPS[key] = out
    return out

def _runs(idx):
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1: out[-1][1] = i
        else: out.append([i, i])
    return out

def pingpong(j, n):
    """Frame j of a loop of n frames played forward then backward (no jump at the wrap)."""
    if n < 2: return 0
    m = j % (2 * n - 2)
    return m if m < n else 2 * n - 2 - m


# ------------------------------------------------------------------ the speaker's own words
def sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def _strip(ws):
    while ws and norm_word(ws[0]["w"]) in FILLERS: ws = ws[1:]
    while ws and norm_word(ws[-1]["w"]) in FILLERS - {"so"}: ws = ws[:-1]
    return ws

def text_of(ws, cap=True):
    t = " ".join(w["w"] for w in ws).strip()
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    if cap and t: t = t[0].upper() + t[1:]
    return t

def chunks(words, maxc=60):
    """His lines cut into readable pieces: whole sentences when short, else the parts between commas, else a run of
    words around a key word. [(text, start time, end time, word dicts)] in the order said."""
    out = []
    for snt in sentences(words):
        snt = _strip(snt)
        if not snt: continue
        txt = text_of(snt)
        if len(txt) <= maxc:
            out.append((txt, snt[0]["s"], snt[-1]["e"], snt)); continue
        part = []
        for w in snt:
            part.append(w)
            if w["w"].endswith(","):
                p = _strip(part)
                if p: out.append((text_of(p).rstrip(","), p[0]["s"], p[-1]["e"], p))
                part = []
        p = _strip(part)
        if p:
            t = text_of(p).rstrip(",")
            if len(t) > maxc:                       # still long: the words up to maxc
                acc = []
                for w in p:
                    if len(text_of(acc + [w])) > maxc: break
                    acc.append(w)
                p = _strip(acc) or p[:6]; t = text_of(p).rstrip(",")
            out.append((t, p[0]["s"], p[-1]["e"], p))
    return [x for x in out if len(re.sub(r"[^\w]", "", x[0])) >= 6]

def near_window(items, t0, t1):
    """Items (text, s, e, ...) sorted: those said in [t0, t1] first (in order), then by distance to the window."""
    def dist(it):
        s, e = it[1], it[2]
        if s >= t0 - 0.3 and s <= t1: return (0, s)
        return (1, min(abs(s - t1), abs(e - t0)))
    return sorted(items, key=dist)

def phrase_with(words, w, before=1, after=4, maxc=34):
    """A short phrase around word w (a dict in words): a few words before and after, inside its sentence."""
    for snt in sentences(words):
        if w in snt:
            k = snt.index(w)
            seg = _strip(snt[max(0, k - before):k + after + 1])
            while seg and len(text_of(seg, False)) > maxc and len(seg) > 2:
                seg = seg[:-1] if seg.index(w) < len(seg) - 1 else seg[1:]
            return text_of(seg, False).rstrip(",.!?")
    return re.sub(r"[^\w'-]", "", w["w"])

DANGLING = set("""a an the and or but so to of in on at for with from by as than my your our i i'm i've i'd like which that
is was be are were really very some put just um uh ever never""".split())
BAD_START = DANGLING - {"i'm", "my", "i", "never", "really"} | {"been", "before", "mentioned", "well", "me"}

def pieces(words):
    """Sentences cut at commas too: [[word dicts], ...]."""
    out = []
    for snt in sentences(words):
        cur = []
        for w in snt:
            cur.append(w)
            if re.search(r"[,;:]$", w["w"]): out.append(cur); cur = []
        if cur: out.append(cur)
    return out

def short_phrases(words, maxc=32, minc=10):
    """Short phrases of the speaker's that read on their own ('better than last year', 'the line was out the door'): runs of 2-6
    words inside a sentence piece that hold a strong word and don't start or end on a dangling word. Best first,
    no two sharing a word. [(text, start, end, word dicts, score)]"""
    from core import key_words as kws
    strong = {id(w) for w in kws(words)}
    cands = []
    for piece in pieces(words):
        n = len(piece)
        for i in range(n):
            for j in range(i + 2, min(n, i + 6) + 1):
                ws = piece[i:j]
                first, last = norm_word(ws[0]["w"]), norm_word(ws[-1]["w"])
                if first in BAD_START or last in DANGLING: continue
                txt = text_of(ws, False).rstrip(",.!?;:")
                if not (minc <= len(txt) <= maxc): continue
                ks = [len(norm_word(w["w"])) for w in ws if id(w) in strong]
                if not ks: continue
                score = max(ks) * 1.5 + 0.5 * sum(ks) + 6 * (j == n) + 3 * (i == 0) - abs(len(txt) - 22) * 0.25
                cands.append((txt, ws[0]["s"], ws[-1]["e"], ws, score))
    cands.sort(key=lambda x: -x[4])
    out, used = [], set()
    for cd in cands:
        ids = {id(w) for w in cd[3]}
        if ids & used: continue
        used |= ids
        out.append(cd)
    return out

def has_strong(text):
    from core import key_words as kws
    return bool(kws([{"w": t} for t in text.split()]))

def clean_word(w):
    return re.sub(r"[^\w'-]", "", w)

def today_line(fmt="long"):
    t = datetime.date.today()
    if fmt == "month": return t.strftime("%B %Y")
    return t.strftime("%B ") + str(t.day) + t.strftime(", %Y")


# ------------------------------------------------------------------ the frame
def solid_small(c, q=4):
    """The cutout at 1/q size, holes filled, as a bool array (cached per frame)."""
    st = c.state
    if st.get("_ss_i") == c.i and st.get("_ss_q") == q: return st["_ss"]
    from scipy.ndimage import binary_fill_holes, label
    m = np.asarray(Image.fromarray((c.mask * 255).astype(np.uint8), "L").resize((W // q, H // q), Image.BILINEAR)) > 127
    lab, n = label(m)
    if n > 1:
        sizes = np.bincount(lab.ravel()); sizes[0] = 0
        m = sizes[lab] >= 0.12 * sizes.max()
    m = binary_fill_holes(m)
    st["_ss"], st["_ss_i"], st["_ss_q"] = m, c.i, q
    return m

def grow_mask(mask, px, feather, q=4):
    """mask (HxW float) grown by px and feathered, from a 1/q copy (fast)."""
    sm = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), "L").resize((W // q, H // q), Image.BILINEAR)
    k = max(3, int(px / q) * 2 + 1)
    sm = sm.filter(ImageFilter.MaxFilter(k if k % 2 else k + 1))
    if feather > 0: sm = sm.filter(ImageFilter.GaussianBlur(feather / q))
    return np.asarray(sm.resize((W, H), Image.BILINEAR), np.float32) / 255
