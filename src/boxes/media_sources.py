"""Direct-API audio and video, from catalogues that publish an openly-licensed
file you can actually fetch and embed.

Parallel renders JavaScript, but its Extract output is markdown, so a page's
`<audio>` / `<video>` elements do not survive it. The hosts that carry open
recordings (archive.org item pages, museum players) hide the file behind a
script or 403 a datacenter IP. Two catalogues expose both a search API and a
direct file URL:

    Wikimedia Commons  MediaWiki API, File namespace. Everything there is
                       CC or public domain by policy.
    archive.org        advancedsearch + per-item metadata; the download URL
                       returns the bytes. Licensing is uneven, so this is
                       gated to explicit CC / public-domain items and a small
                       set of known-open collections.

A `MediaHit` is a `(url, kind, mime, license)` the existing `_fetch` + harvest
path in ``parallel_search`` takes as-is.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

# Commons' API policy wants a descriptive agent with contact info; a generic
# browser string gets throttled or served an HTML error instead of JSON.
_UA = {"User-Agent": "THEBOXES-research/0.1 (Agentic Cinema hackathon; +https://agentic-cinema-boxes.web.app)"}

_AUDIO_EXT = ("ogg", "oga", "mp3", "flac", "wav", "m4a", "opus")
_VIDEO_EXT = ("webm", "mp4", "ogv", "m4v", "mov")
_MIME = {
    "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
    "mp3": "audio/mpeg", "flac": "audio/flac", "wav": "audio/wav", "m4a": "audio/mp4",
    "webm": "video/webm", "mp4": "video/mp4", "ogv": "video/ogg",
    "m4v": "video/mp4", "mov": "video/quicktime",
}
# Fetch caps. ffmpeg trims to a 20 s clip in the container; the fallback trims
# by bytes. Either way, bias hard toward small source files.
_MAX_AUDIO = 30_000_000
_MAX_VIDEO = 60_000_000

# archive.org items are frequently unlabelled. Accept only an explicit open
# licence, or membership in a collection that is open by construction.
_ARCHIVE_OPEN_COLLECTIONS = {
    "prelinger", "prelingerhomemovies", "prelinger_home_movies",
    "librivoxaudio", "nasa", "fedflix", "usfederalgovernment",
    "computerchronicles", "computer_history", "sipacollection",
    "academicfilmarchive", "governmentpublicdomain",
}
_ARCHIVE_OPEN_LICENSE_HINTS = ("creativecommons.org", "/publicdomain/", "publicdomain")


@dataclass
class MediaHit:
    url: str          # direct, fetchable file URL
    kind: str         # "audio" | "video"
    mime: str
    source: str       # "commons" | "archive"
    page_url: str     # human-facing page for citation
    title: str = ""
    license: str = "" # short label where known
    size: int = 0     # bytes, when the catalogue reports it


def _clean_url(u: str) -> str:
    """Drop tracking query params Commons appends to imageinfo URLs."""
    s = urlsplit(u)
    return urlunsplit((s.scheme, s.netloc, s.path, "", ""))


# --------------------------------------------------------------------------- #
# Wikimedia Commons
# --------------------------------------------------------------------------- #
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def commons_media(query: str, *, want: tuple[str, ...] = ("audio", "video"),
                  limit: int = 6, timeout: float = 20.0) -> list[MediaHit]:
    out: list[MediaHit] = []
    for kind in want:
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:{kind} {query}", "gsrnamespace": "6",
            "gsrlimit": str(max(2, limit)), "prop": "imageinfo",
            "iiprop": "url|mediatype|size|mime|extmetadata",
        }
        try:
            r = httpx.get(_COMMONS_API, params=params, headers=_UA, timeout=timeout)
            r.raise_for_status()
            pages = (r.json().get("query") or {}).get("pages") or {}
        except (httpx.HTTPError, ValueError):
            continue
        for pg in pages.values():
            ii = (pg.get("imageinfo") or [{}])[0]
            mtype = (ii.get("mediatype") or "").lower()  # "audio" | "video"
            k = "audio" if mtype == "audio" else "video" if mtype == "video" else ""
            url = _clean_url(ii.get("url") or "")
            if not k or not url:
                continue
            size = int(ii.get("size") or 0)
            if k == "audio" and size and size > _MAX_AUDIO:
                continue
            if k == "video" and size and size > _MAX_VIDEO:
                continue
            em = ii.get("extmetadata") or {}
            lic = (em.get("LicenseShortName") or {}).get("value", "") or "Wikimedia Commons"
            title = pg.get("title") or ""
            page = (
                "https://commons.wikimedia.org/wiki/"
                + quote(title.replace(" ", "_"), safe=":/()") if title else url
            )
            out.append(MediaHit(
                url=url, kind=k,
                mime=ii.get("mime") or _MIME.get(url.rsplit(".", 1)[-1].lower(), f"{k}/octet-stream"),
                source="commons", page_url=page,
                title=title.removeprefix("File:"),
                license=lic, size=size,
            ))
    return out


# --------------------------------------------------------------------------- #
# archive.org
# --------------------------------------------------------------------------- #
_ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
_ARCHIVE_META = "https://archive.org/metadata/"
_ARCHIVE_DL = "https://archive.org/download/"


def _archive_pick_file(files: list[dict], kind: str) -> dict | None:
    exts = _AUDIO_EXT if kind == "audio" else _VIDEO_EXT
    cap = _MAX_AUDIO if kind == "audio" else _MAX_VIDEO
    cands: list[tuple[int, int, dict]] = []
    for f in files:
        name = (f.get("name") or "").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in exts:
            continue
        fmt = (f.get("format") or "").lower()
        if "hevc" in fmt or "mpeg2" in fmt or "10bit" in fmt:
            continue  # masters: huge, and not widely playable
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size and size > cap:
            continue
        cands.append((exts.index(ext), size or 1 << 40, f))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1]))  # preferred ext, then smallest
    return cands[0][2]


def _archive_is_open(meta: dict) -> tuple[bool, str]:
    lic = (meta.get("licenseurl") or meta.get("rights") or "").lower()
    if any(h in lic for h in _ARCHIVE_OPEN_LICENSE_HINTS):
        return True, meta.get("licenseurl") or meta.get("rights") or "open licence"
    coll = meta.get("collection") or []
    coll = {coll} if isinstance(coll, str) else set(coll)
    hit = coll & _ARCHIVE_OPEN_COLLECTIONS
    if hit:
        return True, f"archive.org/{sorted(hit)[0]}"
    return False, ""


def archive_media(query: str, *, want: tuple[str, ...] = ("audio", "video"),
                  limit: int = 6, timeout: float = 20.0) -> list[MediaHit]:
    mt = " OR ".join(("audio" if "audio" in want else "", "movies" if "video" in want else "")).strip(" OR ")
    if not mt:
        return []
    params = {
        "q": f"({query}) AND mediatype:({mt})",
        "fl[]": ["identifier", "title"],
        "rows": str(limit + 3), "output": "json",
        "sort[]": "downloads desc",
    }
    try:
        r = httpx.get(_ARCHIVE_SEARCH, params=params, headers=_UA, timeout=timeout)
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
    except (httpx.HTTPError, ValueError, KeyError):
        return []

    out: list[MediaHit] = []

    def one(doc: dict) -> MediaHit | None:
        ident = doc.get("identifier")
        if not ident:
            return None
        try:
            md = httpx.get(f"{_ARCHIVE_META}{ident}", headers=_UA, timeout=timeout).json()
        except (httpx.HTTPError, ValueError):
            return None
        meta = md.get("metadata") or {}
        ok, lic = _archive_is_open(meta)
        if not ok:
            return None
        raw_mt = (meta.get("mediatype") or "").lower()
        kind = "audio" if raw_mt == "audio" else "video" if raw_mt == "movies" else ""
        if kind not in want:
            return None
        f = _archive_pick_file(md.get("files") or [], kind)
        if not f:
            return None
        name = f["name"]
        ext = name.rsplit(".", 1)[-1].lower()
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return MediaHit(
            url=f"{_ARCHIVE_DL}{ident}/{quote(name)}",
            kind=kind, mime=_MIME.get(ext, f"{kind}/octet-stream"),
            source="archive", page_url=f"https://archive.org/details/{ident}",
            title=str(meta.get("title") or ident), license=lic, size=size,
        )

    probe = docs[: limit + 2]
    with ThreadPoolExecutor(max_workers=min(4, len(probe) or 1)) as ex:
        for hit in ex.map(one, probe):
            if hit:
                out.append(hit)
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- #
# combined
# --------------------------------------------------------------------------- #
def find_media(query: str, *, audio: bool = True, video: bool = True,
               limit: int = 3) -> list[MediaHit]:
    """Openly-licensed audio and video for a research query, lightest first.
    Commons is tried before archive.org: it is smaller, cleaner, and its
    licensing needs no interpretation."""
    want = tuple(k for k, on in (("audio", audio), ("video", video)) if on)
    if not want or not query.strip():
        return []
    hits: list[MediaHit] = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [
            ex.submit(commons_media, query, want=want, limit=limit + 2),
            ex.submit(archive_media, query, want=want, limit=limit + 1),
        ]
        for fu in futs:
            try:
                hits += fu.result()
            except Exception:  # noqa: BLE001
                pass
    seen: set[str] = set()
    uniq: list[MediaHit] = []
    for h in sorted(hits, key=lambda h: (h.source != "commons", h.size or 1 << 40)):
        if h.url in seen:
            continue
        seen.add(h.url)
        uniq.append(h)
    return uniq[:limit]
