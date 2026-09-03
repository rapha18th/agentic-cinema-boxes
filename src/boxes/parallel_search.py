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
# image harvesting: markdown -> bytes -> Gemini Embedding 2 (picture + caption)
# ----------------------------------------------------------------------------- #
_JUNK = ("logo", "icon", "sprite", "avatar", "button", "1x1", "spacer", "pixel",
         "placeholder", "loading", "blank", "/emoji", "favicon", "badge")


def _page_images(page_url: str, timeout: float = 8.0) -> list[tuple[str, str]]:
    """(image_url, alt) pairs from a page: og:image first, then real inline
    images, resolved to absolute URLs, junk filtered."""
    try:
        r = httpx.get(page_url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "the-boxes-research/0.1 (+https://helenia-11f98.web.app)"})
        r.raise_for_status()
        html = r.text
    except (httpx.HTTPError, UnicodeDecodeError):
        return []

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
        low = src.lower()
        if src in seen or any(k in low for k in _JUNK):
            continue
        seen.add(src)
        uniq.append((src, alt))
    return uniq


def _fetch_image(url: str, timeout: float = 8.0) -> tuple[bytes, str] | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "the-boxes-research/0.1"})
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if not ct.startswith("image/") or ct == "image/svg+xml":
        return None
    if not (5_000 <= len(r.content) <= 6_000_000):
        return None
    return r.content, ct


def harvest_images(
    extracted: list[dict], *, objective_id: str, round_no: int, limit: int
) -> list[Evidence]:
    out: list[Evidence] = []
    per_page = max(1, min(2, limit))
    for src in extracted[:3]:  # only the strongest pages, keep the round fast
        if len(out) >= limit:
            break
        page_url = src.get("url", "")
        kept, tried = 0, 0
        for img_url, alt in _page_images(page_url)[:4]:
            if len(out) >= limit or kept >= per_page or tried >= 3:
                break
            tried += 1
            got = _fetch_image(img_url)
            if not got:
                continue
            kept += 1
            data, ctype = got
            caption = alt or src.get("title", "") or "reference image"
            try:
                vec = embed_parts([image_part(data, ctype), _text_part(caption)], dim=768)
            except Exception:  # noqa: BLE001
                continue
            host = urlparse(img_url).netloc.lower()
            ev = Evidence(
                text=f"[image] {caption}",
                url=src.get("url", ""),
                title=caption[:120],
                publish_date=src.get("publish_date"),
                modality="image",
                objective_id=objective_id,
                query="image harvest",
                image_url=img_url,
                round=round_no,
                license_note="likely reusable" if any(d in host for d in _OPEN_MEDIA) else "check rights",
            )
            ev.vector = vec
            out.append(ev)
    return out


def _text_part(s: str):
    from google.genai import types

    return types.Part(text=s)


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
    harvest_images_limit: int = 0,
) -> list[Evidence]:
    """One research pass: search for the objective, extract the top sources,
    harvest a few images, and return evidence units with provenance attached."""
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
        top_urls, objective=objective, search_queries=queries,
        full_content=full_content or harvest_images_limit > 0,
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

    if harvest_images_limit:
        pages = [{"url": h.url, "title": h.title, "publish_date": h.publish_date}
                 for h in hits[: extract_urls + 2]]
        evidence += harvest_images(
            pages, objective_id=objective_id, round_no=round_no,
            limit=harvest_images_limit,
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
