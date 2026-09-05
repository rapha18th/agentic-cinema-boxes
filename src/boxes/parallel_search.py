"""Parallel as the research acquisition engine.

Search finds the right sources for a semantic objective. Extract pulls
objective-specific content from those sources. Together they turn an agent
hypothesis into evidence units. Parallel recommends this pairing for multi-hop
research, and it is what makes THE BOXES a Parallel project rather than a project
that happens to call a search box.

Contracts (Parallel API v1):
  POST https://api.parallel.ai/v1/search
    body {"objective": str, "search_queries": [str], "mode": "advanced"|"fast"|"turbo"}
    resp {"results": [{"url","title","publish_date","excerpts": [str]}], ...}
  POST https://api.parallel.ai/v1/extract
    body {"urls": [str], "objective": str, "search_queries": [str],
          "advanced_settings": {"full_content": true}}
    resp {"results": [{"url","title","publish_date","excerpts": [str],"full_content": str}],
          "errors": [...], "session_id": str}
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from google.genai import types

from . import config
from . import media as media_mod
from .embeddings import embed_parts, image_part
from .evidence import Evidence

_TAG = re.compile(r"<[^>]+>")
_SEARCH_URL = config.PARALLEL_SEARCH_URL
_EXTRACT_URL = _SEARCH_URL.rsplit("/", 1)[0] + "/extract"

# Parallel returns text only. To make Gemini Embedding 2 earn its keep, pictures
# are pulled straight from the pages Parallel surfaced: the og:image and the
# substantive inline images. The bytes are then embedded alongside a caption, so
# a real photograph lands in the same 768-d space as the prose.
_META_IMG = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:url|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_SRC = re.compile(r'\bsrc=["\']([^"\']+)["\']', re.I)
_ALT = re.compile(r'\balt=["\']([^"\']*)["\']', re.I)
_IMG_EXT = re.compile(r"\.(?:png|jpe?g|webp|gif)(?:$|[?&#])", re.I)

# Extra modalities. Gemini Embedding 2 takes PDFs, audio, and video natively, so a
# primary-source scan of a page can drop a document, a newsreel clip, or a
# recording into the same 768-d space as the prose.
_HREF = re.compile(r'<a\b[^>]+href=["\']([^"\']+)["\']', re.I)
_MEDIA_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:audio|og:video|og:video:url|twitter:player:stream)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_AV_TAG = re.compile(r'<(?:source|audio|video)\b[^>]+src=["\']([^"\']+)["\']', re.I)
_EXT_KIND = {
    "pdf": "pdf",
    "mp3": "audio", "wav": "audio", "m4a": "audio", "aac": "audio", "flac": "audio", "oga": "audio",
    "mp4": "video", "webm": "video", "m4v": "video",
}
_MEDIA_EXT = re.compile(r"\.(" + "|".join(_EXT_KIND) + r")(?:$|[?&#])", re.I)
_MIME = {
    "pdf": "application/pdf",
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
    "flac": "audio/flac", "oga": "audio/ogg",
    "mp4": "video/mp4", "webm": "video/webm", "m4v": "video/mp4",
}
_SIZE = {  # (min, max) bytes per kind; audio/video are trimmed after download
    "pdf": (10_000, 12_000_000),
    "audio": (8_000, 60_000_000),
    "video": (60_000, 90_000_000),
}
_GLYPH = {"pdf": "document", "audio": "recording", "video": "clip"}

# Domains whose media is broadly reusable. Used only to annotate a rights note.
_OPEN_MEDIA = ("wikimedia.org", "wikipedia.org", "loc.gov", "nasa.gov", "si.edu",
               "nationalarchives", "archive.org", "flickr.com", "europeana.eu")


def _clean(s: str) -> str:
    return _TAG.sub("", s or "").replace("\xa0", " ").strip()


def _headers(key: str) -> dict:
    return {"x-api-key": key, "Content-Type": "application/json"}


@dataclass
class SearchHit:
    title: str
    url: str
    text: str
    publish_date: str | None = None


def has_key() -> bool:
    return bool(config.parallel_api_key())


# ----------------------------------------------------------------------------- #
# Search
# ----------------------------------------------------------------------------- #
def search(
    query: str,
    *,
    objective: str | None = None,
    extra_queries: list[str] | None = None,
    mode: str = "fast",
    max_results: int = 10,
    timeout: float = 45.0,
) -> list[SearchHit]:
    key = config.parallel_api_key()
    if not key:
        return _stub(query, max_results)
    body = {
        "objective": objective or query,
        "search_queries": [query, *(extra_queries or [])],
        "mode": mode,
    }
    resp = httpx.post(_SEARCH_URL, headers=_headers(key), json=body, timeout=timeout)
    resp.raise_for_status()
    hits: list[SearchHit] = []
    for it in resp.json().get("results", []):
        hits.append(
            SearchHit(
                title=_clean(it.get("title", "")),
                url=it.get("url", ""),
                text=_clean("\n\n".join(it.get("excerpts") or [])),
                publish_date=it.get("publish_date"),
            )
        )
    return hits[:max_results]


# ----------------------------------------------------------------------------- #
# Extract
# ----------------------------------------------------------------------------- #
def extract(
    urls: list[str],
    *,
    objective: str,
    search_queries: list[str] | None = None,
    full_content: bool = True,
    max_chars_total: int | None = 40_000,
    timeout: float = 45.0,
) -> list[dict]:
    key = config.parallel_api_key()
    if not key or not urls:
        return []
    body: dict = {
        "urls": urls[:20],
        "objective": objective,
        "search_queries": search_queries or [],
        "advanced_settings": {"full_content": True} if full_content else {},
    }
    if max_chars_total:
        body["max_chars_total"] = max_chars_total
    try:
        resp = httpx.post(_EXTRACT_URL, headers=_headers(key), json=body, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError):
        # Extract is an enrichment step. If it fails, the caller falls back to
        # search excerpts so a research pass still produces evidence.
        return []
    out: list[dict] = []
    for it in payload.get("results", []):
        raw = it.get("full_content") or "\n\n".join(it.get("excerpts") or [])
        out.append(
            {
                "url": it.get("url", ""),
                "title": _clean(it.get("title", "")),
                "publish_date": it.get("publish_date"),
                "content": _clean(raw),
                "raw": raw[:60_000],  # kept unstripped so image markdown survives
            }
        )
    return out


# ----------------------------------------------------------------------------- #
# asset harvesting: page -> bytes -> Gemini Embedding 2 (media + caption)
# ----------------------------------------------------------------------------- #
_JUNK = ("logo", "icon", "sprite", "avatar", "button", "1x1", "spacer", "pixel",
         "placeholder", "loading", "blank", "/emoji", "favicon", "badge")
# A real browser string: archive.org, LOC, and museum sites (the hosts that
# actually carry open audio and video) serve a stub or a 403 to an unknown
# agent, which is why an audio-rich premise still harvested none.
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _get_html(page_url: str, timeout: float = 8.0) -> str:
    # Best-effort fetch of a third-party page. Malformed scraped URLs fail in
    # whatever way the network stack finds first (bad IDNA host, refused
    # connection, decode error) — none of it should ever take the caller down.
    try:
        r = httpx.get(page_url, timeout=timeout, follow_redirects=True, headers=_UA)
        r.raise_for_status()
        return r.text
    except Exception:  # noqa: BLE001
        return ""


def _page_images(html: str, page_url: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _META_IMG.findall(html):
        out.append((urljoin(page_url, m), ""))
    for tag in _IMG_TAG.findall(html)[:120]:
        s = _SRC.search(tag)
        if not s:
            continue
        src = urljoin(page_url, s.group(1))
        if not src.lower().startswith("http") or not _IMG_EXT.search(src):
            continue
        a = _ALT.search(tag)
        out.append((src, (a.group(1) if a else "").strip()))
    seen, uniq = set(), []
    for src, alt in out:
        if src in seen or any(k in src.lower() for k in _JUNK):
            continue
        seen.add(src)
        uniq.append((src, alt))
    return uniq


def _page_media(html: str, page_url: str) -> list[tuple[str, str]]:
    """(media_url, kind) for pdf / audio / video referenced by the page."""
    cands: list[str] = [urljoin(page_url, u) for u in _MEDIA_META.findall(html)]
    cands += [urljoin(page_url, u) for u in _AV_TAG.findall(html)]
    for href in _HREF.findall(html):
        u = urljoin(page_url, href)
        if _MEDIA_EXT.search(u):
            cands.append(u)
    if _MEDIA_EXT.search(page_url):  # the source itself is a document or clip
        cands.insert(0, page_url)
    out, seen = [], set()
    for u in cands:
        if not u.lower().startswith("http") or u in seen:
            continue
        m = _MEDIA_EXT.search(u)
        if not m:
            continue
        seen.add(u)
        out.append((u, _EXT_KIND[m.group(1).lower()]))
    return out


def _fetch(url: str, *, want: str, timeout: float = 12.0) -> tuple[bytes, str] | None:
    """want: 'image' | 'pdf' | 'audio' | 'video'. Returns (bytes, mime) or None.
    Same rationale as _get_html: a scraped asset URL can be malformed in ways
    that surface anywhere from URL parsing to DNS to the socket layer."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_UA)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    data = r.content
    ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if want == "image":
        if not ct.startswith("image/") or ct == "image/svg+xml":
            return None
        return (data, ct) if 5_000 <= len(data) <= 6_000_000 else None
    lo, hi = _SIZE[want]
    if not (lo <= len(data) <= hi):
        return None
    if want == "pdf":
        if not (data[:5] == b"%PDF-" or ct == "application/pdf"):
            return None
        return data, "application/pdf"
    ext = (_MEDIA_EXT.search(url) or [None, ""])[1].lower()
    # Archive hosts serve downloads as octet-stream; trust the URL extension
    # in that case, and sanity-check the file's magic bytes.
    generic = ct in ("", "application/octet-stream", "binary/octet-stream", "application/download")
    if want == "audio":
        ok = ct.startswith("audio/") or (generic and ext in _MIME and _MIME[ext].startswith("audio/"))
        if not ok or not (data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") or data[:4] in (b"OggS", b"fLaC", b"RIFF") or data[4:8] == b"ftyp"):
            return None
    if want == "video":
        ok = ct.startswith("video/") or (generic and ext in _MIME and _MIME[ext].startswith("video/"))
        if not ok or not (data[4:8] == b"ftyp" or data[:4] == b"\x1aE\xdf\xa3" or data[:4] == b"RIFF"):
            return None
    return data, (ct if ct.startswith(("audio/", "video/")) else _MIME.get(ext, f"{want}/octet-stream"))


def _rights(host: str) -> str:
    return "open-access host · verify item rights" if any(d in host for d in _OPEN_MEDIA) else "rights not verified"


def _page_assets(page: dict, *, images: int, docs: int, av: int) -> list[dict]:
    """Fetch a bounded set of assets off one page. Pure I/O, runs in a thread.
    Returns raw material dicts; embedding happens later, on the main thread."""
    url = page.get("url", "")
    html = _get_html(url)
    if not html:
        return []
    plans: list[tuple[str, str, str]] = []  # (kind, want, media_url)
    for src, _alt in _page_images(html, url)[:3][: max(0, images)]:
        plans.append(("image", "image", src))
    seen_kind = {"pdf": 0, "audio": 0, "video": 0}
    for murl, kind in _page_media(html, url):
        cap = docs if kind == "pdf" else av
        if seen_kind[kind] >= min(2, cap):
            continue
        seen_kind[kind] += 1
        plans.append((kind, kind, murl))

    mats: list[dict] = []
    for kind, want, murl in plans:
        got = _fetch(murl, want=want)
        if not got:
            continue
        data, mime = got
        trimmed = False
        if kind in ("audio", "video"):
            data, mime, trimmed = media_mod.trim_av(data, mime)
        mats.append({
            "kind": kind, "data": data, "mime": mime, "media_url": murl,
            "trimmed": trimmed, "page": page,
        })
    return mats


def harvest_assets(
    pages: list[dict], *, objective_id: str, round_no: int,
    images: int = 0, docs: int = 0, av: int = 0,
) -> list[Evidence]:
    """Pull a few pictures, documents, and recordings off the pages Parallel
    surfaced and embed each with Gemini Embedding 2 as media + caption. Fetching
    runs in parallel; embedding stays sequential (one genai client)."""
    todo = [p for p in pages[:3] if p.get("url")]
    if not todo or not (images or docs or av):
        return []

    with ThreadPoolExecutor(max_workers=min(3, len(todo))) as ex:
        batches = list(ex.map(
            lambda p: _page_assets(p, images=images, docs=docs, av=av), todo
        ))
    mats = [m for b in batches for m in b]

    budget = {"image": images, "pdf": docs, "audio": av, "video": av}
    out: list[Evidence] = []
    for m in mats:
        k = m["kind"]
        if budget.get(k, 0) <= 0:
            continue
        page, media_url, mime = m["page"], m["media_url"], m["mime"]
        caption = (page.get("title") or _GLYPH.get(k, "reference"))[:200]
        try:
            part = image_part(m["data"], mime) if k == "image" else types.Part.from_bytes(
                data=m["data"], mime_type=mime
            )
            vec = embed_parts([part, types.Part(text=caption)], dim=768)
        except Exception:  # noqa: BLE001
            continue
        ev = Evidence(
            text=f"[{k}] {caption}",
            url=page.get("url", ""),
            title=caption[:120],
            publish_date=page.get("publish_date"),
            modality=k,
            objective_id=objective_id,
            query=f"{k} harvest",
            image_url=media_url if k == "image" else "",
            media_url=media_url,
            media_mime=mime,
            media_trimmed=m["trimmed"],
            round=round_no,
            license_note=_rights(urlparse(media_url).netloc.lower()),
        )
        ev.vector = vec
        out.append(ev)
        budget[k] -= 1
    return out


# ----------------------------------------------------------------------------- #
# Search + Extract -> Evidence
# ----------------------------------------------------------------------------- #
def research(
    objective: str,
    queries: list[str],
    *,
    objective_id: str = "",
    mode: str = "fast",
    extract_urls: int = 3,
    full_content: bool = True,
    per_source_chars: int = 1_400,
    round_no: int = 0,
    harvest_images: int = 0,
    harvest_docs: int = 0,
    harvest_av: int = 0,
) -> list[Evidence]:
    """One research pass: search the objective, extract the top sources, harvest a
    few pictures, documents, and recordings, and return evidence with provenance."""
    seen: dict[str, SearchHit] = {}
    for q in queries:
        try:
            hits_q = search(q, objective=objective, mode=mode, max_results=8)
        except httpx.HTTPError:
            hits_q = []
        for h in hits_q:
            if h.url and h.url not in seen:
                seen[h.url] = h
    hits = list(seen.values())
    if not hits:
        return []

    top_urls = [h.url for h in hits[:extract_urls]]
    extracted_list = extract(
        top_urls, objective=objective, search_queries=queries, full_content=full_content,
    )
    extracted = {e["url"]: e for e in extracted_list}

    evidence: list[Evidence] = []
    for h in hits:
        ex = extracted.get(h.url)
        text = (ex["content"] if ex and ex["content"] else h.text)[:per_source_chars].strip()
        if not text and not h.title:
            continue
        evidence.append(
            Evidence(
                text=f"{h.title}. {text}".strip(". ").strip() if h.title else text,
                url=h.url,
                title=h.title or (ex["title"] if ex else ""),
                publish_date=h.publish_date or (ex["publish_date"] if ex else None),
                modality="text",
                objective_id=objective_id,
                query=queries[0] if queries else objective,
                round=round_no,
            )
        )

    if harvest_images or harvest_docs or harvest_av:
        pages = [{"url": h.url, "title": h.title, "publish_date": h.publish_date}
                 for h in hits[: extract_urls + 2]]
        evidence += harvest_assets(
            pages, objective_id=objective_id, round_no=round_no,
            images=harvest_images, docs=harvest_docs, av=harvest_av,
        )
    return evidence


def _stub(query: str, n: int) -> list[SearchHit]:
    return [
        SearchHit(
            title=f"[STUB] {query} result {i + 1}",
            url=f"https://example.invalid/{i + 1}",
            text=f"Placeholder about {query}. Set PARALLEL_API_KEY for live search.",
        )
        for i in range(min(n, 3))
    ]
