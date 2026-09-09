"""Parallel as the research acquisition engine.

Search finds the right sources for a semantic objective. Extract pulls
objective-specific content from those sources. Together they turn an agent
hypothesis into evidence units. Parallel recommends this pairing for multi-hop
research, and it is what makes THE BOXES a Parallel project rather than a project
that happens to call a search box.

Calls go through the parallel-web SDK (`from parallel import Parallel`,
`client.search(...)` / `client.extract(...)`). A raw httpx path to the same v1
endpoints stays as a fallback for when the SDK is absent or a test points
PARALLEL_SEARCH_URL at a local stub.

Contracts (Parallel API v1):
  client.search(objective=str, search_queries=[str], mode="advanced"|"fast"|"turbo")
    -> results[{url, title, publish_date, excerpts: [str]}]
  client.extract(urls=[str], objective=str, search_queries=[str],
                 advanced_settings={"full_content": true})
    -> results[{url, title, publish_date, excerpts: [str], full_content: str}], errors, session_id
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

try:
    from parallel import Parallel  # parallel-web SDK, the first-class client
except Exception:  # SDK not installed in this environment
    Parallel = None

from google.genai import types

from . import config
from . import media as media_mod
from . import media_sources
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
    "mp3": "audio", "wav": "audio", "m4a": "audio", "aac": "audio", "flac": "audio",
    "oga": "audio", "ogg": "audio", "opus": "audio",
    "mp4": "video", "webm": "video", "m4v": "video", "ogv": "video", "mov": "video",
}
_MEDIA_EXT = re.compile(r"\.(" + "|".join(_EXT_KIND) + r")(?:$|[?&#])", re.I)
_MIME = {
    "pdf": "application/pdf",
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
    "flac": "audio/flac", "oga": "audio/ogg", "ogg": "audio/ogg", "opus": "audio/ogg",
    "mp4": "video/mp4", "webm": "video/webm", "m4v": "video/mp4",
    "ogv": "video/ogg", "mov": "video/quicktime",
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


# Book-catalogue and bibliographic-database pages extract as nav chrome plus a
# purchase prompt. They carry a title but no claim, and then dominate the
# contradiction candidates because every one of them mentions the same subject.
_STUB_MARKERS = (
    "request rights and permissions", "download book flyer", "course adoption",
    "go to database home", "bibliographic database", "add to cart", "add to basket",
    "add to wishlist", "table of contents", "leiden university catalogue",
    "request desk copy", "purchase options", "e-book isbn", "eisbn",
)


def _low_value(text: str) -> bool:
    t = (text or "").lower()
    if len(t) < 60:
        return True
    if sum(1 for m in _STUB_MARKERS if m in t) >= 2:
        return True
    letters = sum(c.isalpha() or c.isspace() for c in t)
    return letters / max(len(t), 1) < 0.5


def _headers(key: str) -> dict:
    return {"x-api-key": key, "Content-Type": "application/json"}


def _note(trace: dict | None, **kw) -> None:
    """Accumulate per-call Parallel telemetry onto an optional trace dict.
    Numbers add up across the objectives of a round; strings overwrite."""
    if trace is None:
        return
    for k, v in kw.items():
        if isinstance(v, str):
            trace[k] = v
        else:
            trace[k] = trace.get(k, 0) + v


# The SDK always talks to api.parallel.ai. Tests point PARALLEL_SEARCH_URL at a
# local stub, so when the URL is redirected the raw httpx path runs instead.
_SDK_BASE_URL = "https://api.parallel.ai/v1/search"
_sdk_client = None


def _client(key: str):
    """The parallel-web SDK client, or None when the raw httpx path should run
    (SDK missing, no key, or PARALLEL_SEARCH_URL redirected for a test)."""
    global _sdk_client
    if Parallel is None or not key or config.PARALLEL_SEARCH_URL != _SDK_BASE_URL:
        return None
    if _sdk_client is None:
        _sdk_client = Parallel(api_key=key)
    return _sdk_client


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
    trace: dict | None = None,
) -> list[SearchHit]:
    key = config.parallel_api_key()
    if not key:
        return _stub(query, max_results)

    t0 = time.perf_counter()
    hits: list[SearchHit] = []
    transport = "http"
    client = _client(key)
    if client is not None:
        try:
            hits = _sdk_search(client, query, objective, extra_queries, mode, max_results)
            transport = "sdk"
        except Exception:
            hits, transport = [], "http"  # fall through to the raw request below

    if transport != "sdk":
        body = {
            "objective": objective or query,
            "search_queries": [query, *(extra_queries or [])],
            "mode": mode,
        }
        resp = httpx.post(_SEARCH_URL, headers=_headers(key), json=body, timeout=timeout)
        resp.raise_for_status()
        hits = [
            SearchHit(
                title=_clean(it.get("title", "")),
                url=it.get("url", ""),
                text=_clean("\n\n".join(it.get("excerpts") or [])),
                publish_date=it.get("publish_date"),
            )
            for it in resp.json().get("results", [])
        ][:max_results]

    _note(trace, search_ms=(time.perf_counter() - t0) * 1000,
          search_results=len(hits), search_transport=transport)
    return hits


def _sdk_search(client, query, objective, extra_queries, mode, max_results):
    res = client.search(
        objective=objective or query,
        search_queries=[query, *(extra_queries or [])],
        mode=mode,
        max_chars_total=40_000,
    )
    hits = [
        SearchHit(
            title=_clean(r.title or ""),
            url=r.url or "",
            text=_clean("\n\n".join(r.excerpts or [])),
            publish_date=r.publish_date,
        )
        for r in (res.results or [])
    ]
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
    trace: dict | None = None,
) -> list[dict]:
    key = config.parallel_api_key()
    if not key or not urls:
        _note(trace, extract_status="skipped")
        return []

    t0 = time.perf_counter()
    out: list[dict] = []
    status = "ok"

    client = _client(key)
    used_sdk = False
    if client is not None:
        try:
            out = _sdk_extract(
                client, urls, objective, search_queries, full_content, max_chars_total
            )
            used_sdk = True
        except Exception:
            used_sdk = False  # fall through to the raw request below

    if not used_sdk:
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
            for it in payload.get("results", []):
                raw = it.get("full_content") or "\n\n".join(it.get("excerpts") or [])
                out.append({
                    "url": it.get("url", ""),
                    "title": _clean(it.get("title", "")),
                    "publish_date": it.get("publish_date"),
                    "content": _clean(raw),
                    "raw": raw[:60_000],  # kept unstripped so image markdown survives
                })
        except (httpx.HTTPError, ValueError):
            # Extract is an enrichment step. If it fails, the caller falls back
            # to search excerpts so a research pass still produces evidence.
            status = "error"

    if status == "ok" and not out:
        status = "empty"
    _note(trace, extract_ms=(time.perf_counter() - t0) * 1000,
          extract_count=len(out), extract_status=status)
    return out


def _sdk_extract(client, urls, objective, search_queries, full_content, max_chars_total):
    kwargs: dict = {"urls": urls[:20], "objective": objective}
    if search_queries:
        kwargs["search_queries"] = search_queries
    if full_content:
        kwargs["advanced_settings"] = {"full_content": True}
    if max_chars_total:
        kwargs["max_chars_total"] = max_chars_total
    res = client.extract(**kwargs)
    out: list[dict] = []
    for r in (res.results or []):
        raw = r.full_content or "\n\n".join(r.excerpts or [])
        out.append(
            {
                "url": r.url or "",
                "title": _clean(r.title or ""),
                "publish_date": r.publish_date,
                "content": _clean(raw),
                "raw": raw[:60_000],
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
# Wikimedia enforces its user-agent policy on upload.wikimedia.org and 403s a
# bare browser string. It wants an identifiable client with a contact URL.
_WIKIMEDIA_UA = {
    **_UA,
    "User-Agent": "THEBOXES-research/0.1 (Agentic Cinema hackathon; +https://agentic-cinema-boxes.web.app)",
}


def _ua_for(url: str) -> dict:
    host = urlparse(url).netloc.lower()
    return _WIKIMEDIA_UA if ("wikimedia.org" in host or "wikipedia.org" in host) else _UA


def _get_html(page_url: str, timeout: float = 8.0) -> str:
    # Best-effort fetch of a third-party page. Malformed scraped URLs fail in
    # whatever way the network stack finds first (bad IDNA host, refused
    # connection, decode error) — none of it should ever take the caller down.
    try:
        r = httpx.get(page_url, timeout=timeout, follow_redirects=True, headers=_ua_for(page_url))
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
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_ua_for(url))
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
    # Archive and Commons hosts serve downloads as octet-stream, or Ogg audio
    # and video both as `application/ogg`. Trust the URL extension in those
    # cases, and sanity-check the file's magic bytes either way.
    generic = ct in ("", "application/octet-stream", "binary/octet-stream",
                     "application/download", "application/ogg", "application/x-ogg")
    if want == "audio":
        ok = ct.startswith("audio/") or (generic and ext in _MIME and _MIME[ext].startswith("audio/"))
        if not ok or not (data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") or data[:4] in (b"OggS", b"fLaC", b"RIFF") or data[4:8] == b"ftyp"):
            return None
    if want == "video":
        ok = ct.startswith("video/") or (generic and ext in _MIME and _MIME[ext].startswith("video/"))
        if not ok or not (data[4:8] == b"ftyp" or data[:4] in (b"\x1aE\xdf\xa3", b"RIFF", b"OggS")):
            return None
    if ct.startswith(("audio/", "video/")):
        return data, "audio/wav" if ct == "audio/x-wav" else ct
    return data, _MIME.get(ext, f"{want}/octet-stream")


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


def _media_evidence(
    *, kind: str, data: bytes, mime: str, media_url: str, page_url: str,
    caption: str, publish_date: str | None, objective_id: str, round_no: int,
    trimmed: bool, license_note: str, query: str,
) -> Evidence | None:
    """Embed one harvested asset with Gemini Embedding 2 (media + caption) and
    wrap it as Evidence. Returns None if the embed call fails."""
    caption = (caption or _GLYPH.get(kind, "reference"))[:200]
    try:
        part = image_part(data, mime) if kind == "image" else types.Part.from_bytes(
            data=data, mime_type=mime
        )
        vec = embed_parts([part, types.Part(text=caption)], dim=768)
    except Exception:  # noqa: BLE001
        return None
    ev = Evidence(
        text=f"[{kind}] {caption}",
        url=page_url,
        title=caption[:120],
        publish_date=publish_date,
        modality=kind,
        objective_id=objective_id,
        query=query,
        image_url=media_url if kind == "image" else "",
        media_url=media_url,
        media_mime=mime,
        media_trimmed=trimmed,
        round=round_no,
        license_note=license_note,
    )
    ev.vector = vec
    return ev


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
        page = m["page"]
        ev = _media_evidence(
            kind=k, data=m["data"], mime=m["mime"], media_url=m["media_url"],
            page_url=page.get("url", ""), caption=page.get("title") or "",
            publish_date=page.get("publish_date"), objective_id=objective_id,
            round_no=round_no, trimmed=m["trimmed"], query=f"{k} harvest",
            license_note=_rights(urlparse(m["media_url"]).netloc.lower()),
        )
        if ev is None:
            continue
        out.append(ev)
        budget[k] -= 1
    return out


def harvest_media_catalogs(
    query: str, *, objective_id: str, round_no: int, av: int,
) -> list[Evidence]:
    """Openly-licensed audio and video from Wikimedia Commons and archive.org,
    by direct API. The pages Parallel returns almost never carry a fetchable
    clip; these catalogues do, and they hand back a URL and a licence, not a
    JavaScript player."""
    if av <= 0 or not query.strip():
        return []
    try:
        hits = media_sources.find_media(query, audio=True, video=True, limit=av + 2)
    except Exception:  # noqa: BLE001
        return []
    out: list[Evidence] = []
    for h in hits:
        if len(out) >= av:
            break
        got = _fetch(h.url, want=h.kind)
        if not got:
            continue
        data, mime = got
        data, mime, trimmed = media_mod.trim_av(data, mime)
        if len(data) > 4_000_000:
            continue  # Gemini Embedding 2 rejects a payload this large; skip it
        ev = _media_evidence(
            kind=h.kind, data=data, mime=mime, media_url=h.url, page_url=h.page_url,
            caption=h.title, publish_date=None, objective_id=objective_id,
            round_no=round_no, trimmed=trimmed, query=f"{h.kind} catalog: {h.source}",
            license_note=f"{h.source} · {h.license}" if h.license else h.source,
        )
        if ev is not None:
            out.append(ev)
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
    media_key: str = "",
    trace: dict | None = None,
) -> list[Evidence]:
    """One research pass: search the objective, extract the top sources, harvest a
    few pictures, documents, and recordings, and return evidence with provenance."""
    tr = trace if trace is not None else {}
    seen: dict[str, SearchHit] = {}
    for q in queries:
        try:
            hits_q = search(q, objective=objective, mode=mode, max_results=8, trace=tr)
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
        full_content=full_content, trace=tr,
    )
    extracted = {e["url"]: e for e in extracted_list}

    evidence: list[Evidence] = []
    for h in hits:
        ex = extracted.get(h.url)
        text = (ex["content"] if ex and ex["content"] else h.text)[:per_source_chars].strip()
        if not text and not h.title:
            tr["rejected"] = tr.get("rejected", 0) + 1
            continue
        if _low_value(text):
            tr["rejected"] = tr.get("rejected", 0) + 1
            continue  # a library catalogue page or a nav shell, no claims to weigh
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

    # The page scan rarely finds a fetchable clip. Top up the audio/video
    # budget from the open catalogues, keyed on the objective itself.
    if harvest_av:
        got_av = sum(1 for e in evidence if e.modality in ("audio", "video"))
        if got_av < harvest_av:
            evidence += harvest_media_catalogs(
                media_key or objective or (queries[0] if queries else ""),
                objective_id=objective_id, round_no=round_no,
                av=harvest_av - got_av,
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


# ----------------------------------------------------------------------------- #
# Task API: one deep, traceable research pass for the deepest depth
# ----------------------------------------------------------------------------- #
_TASK_PROCESSOR = os.environ.get("BOXES_TASK_PROCESSOR", "core")


def task_deep_dive(question: str, *, wait_s: int = 240) -> dict | None:
    """Run one Parallel Task API job on a focused question and return its written
    answer plus citations. Task is built for multi-step research, so the deepest
    depth gets one. Returns None on any failure or timeout; never raises."""
    key = config.parallel_api_key()
    client = _client(key)
    if client is None or not question.strip():
        return None
    try:
        run = client.task_run.create(input=question.strip(), processor=_TASK_PROCESSOR)
        res = client.task_run.result(run.run_id, api_timeout=wait_s)
        out = res.output
        content = out.content
        if isinstance(content, dict):
            content = content.get("output") or content.get("answer") or next(
                (v for v in content.values() if isinstance(v, str)), ""
            )
        text = str(content or "")
        cites: list[dict] = []
        for fb in (getattr(out, "basis", None) or []):
            for c in (getattr(fb, "citations", None) or []):
                url = getattr(c, "url", "") or ""
                if url and url not in {x["url"] for x in cites}:
                    cites.append({"url": url, "title": getattr(c, "title", "") or url})
        return {"text": text.strip(), "citations": cites, "processor": _TASK_PROCESSOR}
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- #
# Monitor API: keep watching a topic after the run finishes (pull model)
# ----------------------------------------------------------------------------- #
def monitor_start(query: str, *, frequency: str = "1d") -> dict:
    """Create a Parallel Monitor on a research question. Returns
    {"monitor_id": ...} or {"status": "unavailable"} when the API is not
    reachable on this key."""
    client = _client(config.parallel_api_key())
    if client is None or not query.strip():
        return {"status": "unavailable"}
    try:
        m = client.monitor.create(
            frequency=frequency, type="event_stream",
            settings={"query": query.strip()}, processor="lite",
        )
        return {"monitor_id": m.monitor_id, "status": getattr(m, "status", "active"),
                "frequency": frequency}
    except Exception:  # noqa: BLE001
        return {"status": "unavailable"}


def monitor_updates(monitor_id: str, *, limit: int = 20) -> list[dict]:
    client = _client(config.parallel_api_key())
    if client is None or not monitor_id:
        return []
    try:
        page = client.monitor.events(monitor_id, limit=limit)
        out: list[dict] = []
        for e in (getattr(page, "events", None) or getattr(page, "data", None) or []):
            out.append({
                "type": getattr(e, "type", ""),
                "at": str(getattr(e, "created_at", "") or ""),
                "summary": (getattr(e, "message", "") or getattr(e, "summary", "") or "")[:400],
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def monitor_stop(monitor_id: str) -> bool:
    client = _client(config.parallel_api_key())
    if client is None or not monitor_id:
        return False
    try:
        client.monitor.cancel(monitor_id)
        return True
    except Exception:  # noqa: BLE001
        return False
