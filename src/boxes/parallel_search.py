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

import httpx

from . import config
from .evidence import Evidence

_TAG = re.compile(r"<[^>]+>")
_SEARCH_URL = config.PARALLEL_SEARCH_URL
_EXTRACT_URL = _SEARCH_URL.rsplit("/", 1)[0] + "/extract"


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
        body_text = _clean(it.get("full_content") or "") or _clean(
            "\n\n".join(it.get("excerpts") or [])
        )
        out.append(
            {
                "url": it.get("url", ""),
                "title": _clean(it.get("title", "")),
                "publish_date": it.get("publish_date"),
                "content": body_text,
            }
        )
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
) -> list[Evidence]:
    """One research pass: search for the objective, extract the top sources, and
    return evidence units with provenance attached."""
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
    extracted = {
        e["url"]: e
        for e in extract(
            top_urls, objective=objective, search_queries=queries, full_content=full_content
        )
    }

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
            )
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
