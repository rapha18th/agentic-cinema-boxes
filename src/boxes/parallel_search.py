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
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from google.genai import types

from . import config
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
_SIZE = {  # (min, max) bytes per kind
    "pdf": (10_000, 12_000_000),
    "audio": (8_000, 9_000_000),
    "video": (60_000, 14_000_000),
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
_UA = {"User-Agent": "the-boxes-research/0.1 (+https://helenia-11f98.web.app)"}


def _get_html(page_url: str, timeout: float = 8.0) -> str:
    try:
        r = httpx.get(page_url, timeout=timeout, follow_redirects=True, headers=_UA)
        r.raise_for_status()
        return r.text
    except (httpx.HTTPError, UnicodeDecodeError):
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
    """want: 'image' | 'pdf' | 'audio' | 'video'. Returns (bytes, mime) or None."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_UA)
        r.raise_for_status()
    except httpx.HTTPError:
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
    if want == "audio" and not ct.startswith("audio/"):
        return None
    if want == "video" and not ct.startswith("video/"):
        return None
    ext = (_MEDIA_EXT.search(url) or [None, ""])[1].lower()
    return data, (ct if "/" in ct else _MIME.get(ext, f"{want}/octet-stream"))


def _rights(host: str) -> str:
    return "likely reusable" if any(d in host for d in _OPEN_MEDIA) else "check rights"


def harvest_assets(
    pages: list[dict], *, objective_id: str, round_no: int,
    images: int = 0, docs: int = 0, av: int = 0,
) -> list[Evidence]:
    """Pull a few pictures, documents, and recordings off the pages Parallel
    surfaced and embed each one with Gemini Embedding 2 as media + caption."""
    out: list[Evidence] = []
    n_img = n_doc = n_av = 0

    def add(kind: str, media_url: str, caption: str, page: dict, want: str) -> bool:
        got = _fetch(media_url, want=want)
        if not got:
            return False
        data, mime = got
        try:
            part = image_part(data, mime) if want == "image" else types.Part.from_bytes(
                data=data, mime_type=mime
            )
            vec = embed_parts([part, types.Part(text=caption)], dim=768)
        except Exception:  # noqa: BLE001
            return False
        ev = Evidence(
            text=f"[{kind}] {caption}",
            url=page.get("url", ""),
            title=caption[:120],
            publish_date=page.get("publish_date"),
            modality=kind,
            objective_id=objective_id,
            query=f"{kind} harvest",
            image_url=media_url if kind == "image" else "",
            media_url=media_url,
            media_mime=mime,
            round=round_no,
            license_note=_rights(urlparse(media_url).netloc.lower()),
        )
        ev.vector = vec
        out.append(ev)
        return True

    for page in pages[:3]:
        if n_img >= images and n_doc >= docs and n_av >= av:
            break
        html = _get_html(page.get("url", ""))
        if not html:
            continue

        kept = 0
        for src, alt in (_page_images(html, page["url"])[:4] if n_img < images else []):
            if n_img >= images or kept >= 2:
                break
            if add("image", src, alt or page.get("title", "") or "reference image", page, "image"):
                n_img += 1
                kept += 1

        for murl, kind in _page_media(html, page["url"]):
            if kind == "pdf" and n_doc >= docs:
                continue
            if kind in ("audio", "video") and n_av >= av:
                continue
            cap = page.get("title", "") or _GLYPH[kind]
            if add(kind, murl, cap, page, kind):
                if kind == "pdf":
                    n_doc += 1
                else:
                    n_av += 1
            if n_doc >= docs and n_av >= av:
                break
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
