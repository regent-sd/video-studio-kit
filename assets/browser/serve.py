"""The Asset Library page inside Video Review. review/review.py loads this file on first use and hands it every
request under /assets:

    handle(h, method, u)    h: the request handler (send_bytes, send_json, send_response, send_header,
                            end_headers, wfile); method: "GET" or "POST"; u: urllib.parse.urlsplit(path)

  GET /assets               the page (page.html with the local config)
  GET /assets/data          the slim catalog, rebuilt whenever the catalog, media.json or the previews change
  GET /assets/thumb/<name>  a 640 px preview from the cache (file names only; no paths)

Raises FileNotFoundError / PermissionError, which review.py turns into 404 / 403.
summary() gives the Studio page a one-line status (or None when there's no Asset Library yet).
"""
import gzip
import json
import re
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import slim  # noqa: E402

PAGE = HERE / "page.html"
SKELETON = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '</head><body>\n')
LOCAL_CFG = {"mode": "local", "data": "/assets/data", "thumb": "/assets/thumb/", "home": "/studio"}
NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}\.jpg$")
_lock, _cache = threading.Lock(), {"sig": None, "body": None}


def page_html(cfg):
    return PAGE.read_text().replace("/*CONFIG*/{}", json.dumps(cfg))


def _sig():
    def mt(p):
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return 0
    return (mt(slim.al.CATALOG), mt(slim.al.MEDIA_FILE), mt(slim.THUMBS))


def data_bytes():
    sig = _sig()
    with _lock:
        if _cache["sig"] != sig:
            body = json.dumps(dict(slim.slim(slim.load(), local=True), mode="local"), ensure_ascii=False, separators=(",", ":"))
            _cache.update(sig=sig, body=gzip.compress(body.encode(), 6))
        return _cache["body"]


def summary():
    """{"files", "unique", "tagged", "previews", "generated"} for a Studio tile, or None before the first scan."""
    if not slim.al.CATALOG.exists():
        return None
    doc = slim.load()
    g = slim.groups(doc["assets"])
    return {"files": len(doc["assets"]), "unique": len(g),
            "tagged": sum(1 for ms in g.values() if any(m.get("description") for m in ms)),
            "previews": sum(1 for ms in g.values() if slim.thumb_of(ms)), "generated": doc.get("generated")}


def handle(h, method, u):
    if method != "GET":
        return h.send_json({"error": "read only"}, 405)
    if u.path in ("/assets", "/assets/"):
        return h.send_bytes((SKELETON + page_html(LOCAL_CFG) + "\n</body></html>").encode(), "text/html; charset=utf-8")
    if u.path == "/assets/data":
        b = data_bytes()
        h.send_response(200)
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Encoding", "gzip")
        h.send_header("Content-Length", str(len(b)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(b)
        return
    if u.path.startswith("/assets/thumb/"):
        name = u.path[len("/assets/thumb/"):]
        if not NAME.match(name):
            raise PermissionError("bad preview name")
        p = (slim.THUMBS / name).resolve()
        if p.parent != slim.THUMBS.resolve() or not p.is_file():
            raise FileNotFoundError(name)
        return h.send_bytes(p.read_bytes(), "image/jpeg", cache=True)
    h.send_json({"error": "not found"}, 404)
