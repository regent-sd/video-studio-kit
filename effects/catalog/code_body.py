"""Code body: you become a figure made of monospaced characters (your own words, repeated), green-white on black,
with dim code rain behind. A scanline wipes you into code and back out."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, f32, to_pil, font, SFMONO, hexc, ease_io, ease_out, prog, clamp01
from ._print import blur, smooth, solid

NAME = "code-body"
KIND = "restyle"
ABOUT = "You, rebuilt from monospaced characters of your own words, with code rain behind"
DUR = 3.0
PARAMS = dict(
    text=None,          # the characters you're made of; default the words you say in the window (repeated)
    cell=20,            # character cell height in px (width is 0.6 of it); smaller = more detail
    color="#3CFF8F",    # code colour; the brightest parts go toward white
    rain=0.6,           # background code rain strength (0 = off)
    glow=0.45,          # bloom on the characters
    transition="scan",  # scan (a scanline wipes down) | dissolve (characters flip in at random)
    crawl=4.0,          # characters per second the text crawls along each row (0 = still)
)
RAIN_CHARS = ":;=+*<>/\\{}[]()|_-~#$%&"
RAMP = " \u00b7:;"         # the darkest tones, darkest first; brighter cells get the letters of your words
BG = np.array([3, 8, 6], np.float32)

def _atlas(chars, cw, ch):
    """Glyph alpha masks: (2 weights, len(chars), ch, cw) float32."""
    out = np.zeros((2, len(chars), ch, cw), np.float32)
    size = ch * 0.86
    for wi, wt in enumerate((560, 820)):
        f = font(size, wt, SFMONO)
        asc, desc = f.getmetrics()
        for k, chx in enumerate(chars):
            im = Image.new("L", (cw * 3, ch * 3), 0)
            d = ImageDraw.Draw(im)
            d.text((cw * 1.5, ch * 1.5), chx, font=f, fill=255, anchor="mm")
            out[wi, k] = np.asarray(im.crop((cw, ch, cw * 2, ch * 2)), np.float32) / 255.0
    return out

def _setup(c):
    st = c.state
    ch = int(max(10, c.p["cell"])); cw = max(6, int(round(ch * 0.6)))
    cols, rows = -(-W // cw), -(-H // ch)
    txt = c.p.get("text")
    spoken = []                                   # (start, end) of each word in the stream, when it's your words
    if not txt:
        ws = c.words_in() or c.words
        if ws:
            txt = " ".join(w["w"] for w in ws); spoken = [(w["s"], w.get("e", w["s"] + 0.3)) for w in ws]
        else:
            txt = "<> {} [] /* */ => == ++ ::"     # no transcript: plain code symbols
    toks = str(txt).upper().split()
    if len(spoken) != len(toks): spoken = []
    stream, wid = [], []
    for k, tk in enumerate(toks):
        stream += list(tk); wid += [k] * len(tk)
        stream.append("\u00b7"); wid.append(-1)
    stream += ["\u00b7"]; wid += [-1]
    chars = sorted(set(stream) | set(RAIN_CHARS) | set(RAMP) | {" "})
    idx = {k: i for i, k in enumerate(chars)}
    st.update(cw=cw, ch=ch, cols=cols, rows=rows, atlas=_atlas(chars, cw, ch),
              stream=np.array([idx[k] for k in stream], np.int32), wid=np.array(wid, np.int32), spoken=spoken,
              space=idx[" "], dot=idx["\u00b7"], ramp=np.array([idx[k] for k in RAMP], np.int32))
    txt = "".join(toks)
    rng = np.random.default_rng(11)
    pool = np.array([idx[k] for k in (RAIN_CHARS + txt.replace(" ", "") * 2)], np.int32)
    st["pool"] = pool
    st["rain_chars"] = pool[rng.integers(0, len(pool), (rows, cols))]
    st["rain_speed"] = rng.uniform(7, 20, cols).astype(np.float32)
    st["rain_len"] = rng.uniform(6, 22, cols).astype(np.float32)
    st["rain_phase"] = rng.uniform(0, rows * 2, cols).astype(np.float32)
    st["rain_on"] = (rng.random(cols) < 0.62).astype(np.float32)
    st["cell_rand"] = rng.random((rows, cols)).astype(np.float32)
    st["row_dir"] = np.where(np.arange(rows) % 2 == 0, 1, -1).astype(np.int32)
    col = np.array(hexc(c.p["color"]), np.float32)
    st["col"] = col
    st["dim"] = col * 0.22
    st["white"] = np.array([226, 255, 236], np.float32)

def _cells(a, rows, cols, ch, cw):
    """Mean of a HxW array over each character cell -> rows x cols."""
    p = np.zeros((rows * ch, cols * cw), np.float32)
    p[:a.shape[0], :a.shape[1]] = a
    if rows * ch > a.shape[0]: p[a.shape[0]:] = p[a.shape[0] - 1]
    if cols * cw > a.shape[1]: p[:, a.shape[1]:] = p[:, a.shape[1] - 1:a.shape[1]]
    return p.reshape(rows, ch, cols, cw).mean((1, 3))

def _code_frame(c):
    """The full code picture for this frame: float32 HxWx3."""
    st = c.state
    cw, ch, cols, rows = st["cw"], st["ch"], st["cols"], st["rows"]
    u, fi = c.u, c.i
    src = f32(c.src)
    L = (src[..., 0] * 0.3 + src[..., 1] * 0.59 + src[..., 2] * 0.11) / 255.0
    lc = _cells(L, rows, cols, ch, cw)
    mc = _cells(solid(c.mask), rows, cols, ch, cw)
    fig = mc > 0.42
    # tones inside the figure: global stretch mixed with local contrast, so the face reads
    if fig.sum() > 20:
        a, b = np.percentile(lc[fig], [3, 98])
    else:
        a, b = 0.05, 0.9
    g = np.clip((lc - a) / max(0.05, b - a), 0, 1)
    mu = blur(lc, 3.0); sd = np.sqrt(np.maximum(blur((lc - mu) ** 2, 3.0), 1e-5))
    loc = np.clip(0.5 + (lc - mu) / (sd * 4.0 + 0.02), 0, 1)
    v = np.clip(0.55 * g + 0.45 * loc, 0, 1) ** 0.9
    # edge cells of the figure get a bright outline
    pad = np.pad(fig, 1, mode="edge")
    edge = fig & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    # which character: your words, crawling along each row
    n = len(st["stream"])
    shift = int(u * c.p["crawl"]) if c.p["crawl"] else 0
    rr, cc = np.mgrid[0:rows, 0:cols]
    pos = (rr * max(7, int(n * 0.382)) + cc - st["row_dir"][:, None] * shift) % n
    gi = st["stream"][pos]
    # glitch: a few cells flicker to other characters each frame
    rng = np.random.default_rng(fi * 7 + 3)
    gl = rng.random((rows, cols)) < 0.02
    gi = np.where(gl, st["pool"][rng.integers(0, len(st["pool"]), (rows, cols))], gi)
    dk = fig & (v < 0.38)
    gi = np.where(dk, st["ramp"][np.clip((v / 0.38 * len(st["ramp"])).astype(np.int32), 0, len(st["ramp"]) - 1)], gi)
    # the word being said right now lights up white wherever it appears in you
    hot = np.zeros((rows, cols), bool)
    if st["spoken"]:
        now = [k for k, (s0, s1) in enumerate(st["spoken"]) if s0 - 0.04 <= c.t <= max(s1, s0 + 0.25) + 0.12]
        if now: hot = fig & np.isin(st["wid"][pos], now)
    # background rain
    head = (st["rain_phase"] + u * st["rain_speed"]) % (rows + 30)
    dist = head[None, :] - rr
    tail = np.clip(1 - dist / st["rain_len"][None, :], 0, 1)
    rain = np.where(dist >= 0, tail ** 1.6, 0.0)
    rain = rain * st["rain_on"][None, :] * c.p["rain"]
    reroll = rng.random((rows, cols)) < 0.04
    st["rain_chars"] = np.where(reroll, st["pool"][rng.integers(0, len(st["pool"]), (rows, cols))], st["rain_chars"])
    rain_head = (dist >= 0) & (dist < 1)
    gi = np.where(fig, gi, st["rain_chars"])
    # brightness and weight per cell
    bright = np.where(fig, 0.06 + 0.94 * v ** 1.7, rain * 0.55)
    bright = np.where(fig & edge, np.maximum(bright, 0.85), bright)
    bright = np.where(~fig & rain_head, rain * 0.9, bright)
    bright = np.where(hot, 1.0, bright)
    bold = (fig & (v > 0.62)) | (fig & edge) | hot
    gi = np.where(~fig & (bright < 0.02), st["space"], gi)
    alpha = st["atlas"][bold.astype(np.int32), gi]                       # rows, cols, ch, cw
    alpha = alpha.transpose(0, 2, 1, 3).reshape(rows * ch, cols * cw)[:H, :W]
    # colour: dark green -> code colour -> white at the top end
    col, white = st["col"], st["white"]
    b3 = bright[..., None]
    cc_ = np.where(b3 < 0.72, st["dim"] + (col - st["dim"]) * (b3 / 0.72), col + (white - col) * ((b3 - 0.72) / 0.28))
    cc_ = cc_ * np.where(fig, 1.0, 0.85)[..., None]
    colimg = np.repeat(np.repeat(cc_.astype(np.float32), ch, 0), cw, 1)[:H, :W]
    out = BG[None, None, :] + alpha[..., None] * colimg
    # a faint phosphor image of you under the characters, so the face reads at a glance
    vm = (fig * v ** 1.3).astype(np.float32)
    under = np.asarray(Image.fromarray(vm, "F").resize((cols * cw, rows * ch), Image.BILINEAR), np.float32)[:H, :W]
    out += blur(under, 5, 2)[..., None] * col * 0.3
    if c.p["glow"] > 0:
        out += blur(out, 10, 4) * c.p["glow"] * 0.9
    # fine scanlines
    sl = 0.9 + 0.1 * (np.arange(H) % 3 != 0)
    out *= sl[:, None, None]
    return out, rows, cols, ch, cw

def render(c):
    st = c.state
    if "atlas" not in st: _setup(c)
    code, rows, cols, ch, cw = _code_frame(c)
    vid = f32(np.asarray(c.img))
    # transition: a scanline front sweeps down (in), then down again at the end (out)
    tin = min(0.75, c.d * 0.3); tout = min(0.65, c.d * 0.28)
    p_in = ease_io(prog(c.u, 0, tin)); p_out = ease_io(prog(c.u, c.d - tout, tout))
    band = 220.0
    yc = (np.arange(rows) + 0.5) * ch
    rnd = st["cell_rand"]
    if c.p["transition"] == "dissolve":
        thr = rnd * H
        fin, fout = p_in * (H + band), p_out * (H + band)
    else:
        thr = yc[:, None] + rnd * band * 0.8
        fin, fout = p_in * (H + band), p_out * (H + band)
    m_in = (fin >= thr).astype(np.float32)
    m_out = (fout >= thr).astype(np.float32)
    m = m_in * (1 - m_out)
    full = np.repeat(np.repeat(m, ch, 0), cw, 1)[:H, :W]
    out = vid * (1 - full[..., None]) + code * full[..., None]
    # cells flash white as they flip, and the scan front glows
    fl = np.clip(1 - (fin - thr) / 70.0, 0, 1) * m_in * (p_in < 1) * (1 - m_out)
    flash = np.repeat(np.repeat(fl.astype(np.float32), ch, 0), cw, 1)[:H, :W]
    out += flash[..., None] * np.array([80, 150, 105], np.float32)
    if c.p["transition"] != "dissolve":
        yy = np.arange(H, dtype=np.float32)
        for f, on in ((fin, 0 < p_in < 1), (fout, 0 < p_out < 1)):
            if not on: continue
            g = np.exp(-((yy - f) / 3.0) ** 2) + 0.4 * np.exp(-((yy - f) / 26.0) ** 2) + 0.12 * np.exp(-((yy - f) / 90.0) ** 2)
            out += g[:, None, None] * np.array([150, 255, 190], np.float32)[None, None, :] * 0.9
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the characters are your own words in the window",
    "needs": ["person"],
}
