"""A brand's colours and fonts as CSS, for pages Chrome renders (HyperFrames films, Remotion).

    import brandcss
    css = brandcss.fonts_css(b, assets / "fonts", "assets/fonts")   # @font-face rules + a .font-<role> class each
    fam, weight, style = brandcss.font_family(b, "title")           # for inline styles
    files = brandcss.font_files(b, out_dir)                         # {role: copied file name}, for Remotion
    brandcss.on(b, "accent")                                        # the brand colour that reads best on an accent fill

Every font role becomes a real font file next to the page, named brand-<role>. Renderers like
HyperFrames swap well-known system font names for their own stand-ins, so naming "Avenir Next"
isn't enough; a file always renders the same. A face inside a .ttc collection is copied out
into its own .ttf. The copies stay in your work folder, never in the kit.
"""
from __future__ import annotations

import re
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import studio_config as sc  # noqa: E402

ROLE_WEIGHT = {"title": 800, "heading": 700, "caption": 700, "number": 700, "body": 500}
WEIGHTS = [("ultra light", 200), ("extra light", 200), ("thin", 100), ("light", 300), ("regular", 400), ("book", 400),
           ("medium", 500), ("demi bold", 600), ("semibold", 600), ("semi bold", 600), ("extra bold", 800),
           ("ultra bold", 800), ("bold", 700), ("heavy", 800), ("black", 900)]
SERIF_HINT = re.compile(r"new york|georgia|didot|baskerville|hoefler|garamond|times|serif", re.I)


def _spec(b: dict, role: str):
    return (b.get("fonts") or {}).get(role) or sc.DEFAULT_FONTS.get(role, "SF Pro")


def _weight(b: dict, role: str) -> int:
    """The weight to ask for: from the font's name ('... Demi Bold' = 600) or the role's usual weight.
    A single static face renders as itself whatever the weight; variable fonts (SF Pro, New York) use it."""
    spec = _spec(b, role)
    name = spec if isinstance(spec, str) else str(spec.get("name") or spec.get("file") or "")
    n = re.sub(r"\s*\bitalic\b", "", Path(name).stem.replace("-", " "), flags=re.I).strip().lower()
    for word, w in WEIGHTS:
        if n.endswith(" " + word) or n.endswith(word.replace(" ", "")):
            return w
    return ROLE_WEIGHT.get(role, 500)


def _generic(b: dict, role: str) -> str:
    spec = _spec(b, role)
    return "serif" if SERIF_HINT.search(str(spec)) else "sans-serif"


def font_family(b: dict, role: str) -> tuple[str, int, str]:
    """(CSS font-family value, weight, style) for a role."""
    spec = str(_spec(b, role))
    return f"'brand-{role}', {_generic(b, role)}", _weight(b, role), ("italic" if re.search(r"italic", spec, re.I) else "normal")


def extract_ttc_face(src: Path, index: int, dst: Path) -> Path:
    """Copy one face out of a TrueType/OpenType collection (.ttc) into a standalone font file."""
    data = src.read_bytes()
    if data[:4] != b"ttcf":
        raise ValueError(f"{src} is not a font collection")
    off = struct.unpack(">I", data[12 + 4 * index:16 + 4 * index])[0]
    version, n = struct.unpack(">IH", data[off:off + 6])
    recs = [struct.unpack(">4sIII", data[off + 12 + 16 * i:off + 28 + 16 * i]) for i in range(n)]
    sel = max(k for k in range(16) if 2 ** k <= n)
    header = struct.pack(">IHHHH", version, n, 2 ** sel * 16, sel, n * 16 - 2 ** sel * 16)
    pos, dir_, body, head_at = 12 + 16 * n, b"", b"", None
    for tag, chk, toff, tlen in recs:
        tdata = bytearray(data[toff:toff + tlen])
        if tag == b"head":
            tdata[8:12] = b"\0\0\0\0"          # checkSumAdjustment, set below
            head_at = pos
        dir_ += struct.pack(">4sIII", tag, chk, pos, tlen)
        pad = (-len(tdata)) % 4
        body += bytes(tdata) + b"\0" * pad
        pos += len(tdata) + pad
    font = bytearray(header + dir_ + body)
    if head_at is not None:
        total = sum(struct.unpack(f">{len(font) // 4}I", bytes(font) + b"\0" * ((-len(font)) % 4))[0:]) & 0xFFFFFFFF
        font[head_at + 8:head_at + 12] = struct.pack(">I", (0xB1B0AFBA - total) & 0xFFFFFFFF)
    dst.write_bytes(bytes(font))
    return dst


def font_files(b: dict, out_dir: Path) -> dict[str, str]:
    """Copy each role's font into out_dir as brand-<role>.<ext>; returns {role: file name}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for role in sc.DEFAULT_FONTS:
        path, index = sc.font(b, role)
        p = Path(path)
        if p.suffix.lower() == ".ttc" or index:
            dst = extract_ttc_face(p, index, out_dir / f"brand-{role}.ttf")
        else:
            dst = out_dir / f"brand-{role}{p.suffix.lower()}"
            shutil.copy(p, dst)
        files[role] = dst.name
    return files


def fonts_css(b: dict, fonts_dir: Path, url_prefix: str = "assets/fonts") -> str:
    """@font-face rules (fonts copied into fonts_dir) plus a .font-<role> class for every role."""
    out = []
    for role, fname in font_files(b, fonts_dir).items():
        out.append(f"@font-face {{ font-family: 'brand-{role}'; src: url('{url_prefix}/{fname}'); "
                   f"font-weight: 1 1000; font-style: normal; font-display: block; }}")
        fam, w, style = font_family(b, role)
        out.append(f".font-{role} {{ font-family: {fam}; font-weight: {w}; font-style: {style}; }}")
    return "\n    ".join(out)


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def on(b: dict, fill_role: str) -> str:
    """The brand colour (text or on_dark) that reads best on a fill of `fill_role`."""
    fill = sc.hex_color(b, fill_role)
    dark, light = sc.hex_color(b, "text"), sc.hex_color(b, "on_dark")
    return dark if contrast(fill, dark) >= contrast(fill, light) else light


def rgba(b: dict, role: str, alpha: float) -> str:
    r, g, bl = sc.color(b, role)
    return f"rgba({r}, {g}, {bl}, {alpha})"
