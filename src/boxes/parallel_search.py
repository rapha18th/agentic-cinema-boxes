"""Parallel Search API client.

Partner integration for the hackathon Parallel track. The Search API call sits on
the agent's hot path and runs on every research pass.

Contract (Parallel Search API, v1):
  POST https://api.parallel.ai/v1/search
  headers: x-api-key, Content-Type: application/json
  body:   {"objective": str, "search_queries": [str, ...], "mode": "advanced"|"fast"|"turbo"}
  resp:   {"search_id", "results": [{"url", "title", "publish_date", "excerpts": [str]}],
           "warnings", "usage", "session_id"}

The Search API returns text excerpts and URLs. Images for the multimodal index
come from the director's own references and from fetching result pages, not from
this call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from . import config

_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return _TAG.sub("", s).replace("\xa0", " ").strip()


@dataclass
class SearchHit:
    title: str
    url: str
    text: str
    publish_date: str | None = None
    image_url: str | None = None
    source: str = "parallel"


def _parse(payload: dict) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for it in payload.get("results", []):
        excerpts = it.get("excerpts") or []
        hits.append(
            SearchHit(
                title=_clean(it.get("title", "")),
                url=it.get("url", ""),
                text=_clean("\n\n".join(excerpts)),
                publish_date=it.get("publish_date"),
            )
        )
    return hits


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
    resp = httpx.post(
        config.PARALLEL_SEARCH_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse(resp.json())[:max_results]


def _stub(query: str, n: int) -> list[SearchHit]:
    return [
        SearchHit(
            title=f"[STUB] {query} result {i + 1}",
            url=f"https://example.invalid/{i + 1}",
            text=f"Placeholder text about {query}. Replace by setting PARALLEL_API_KEY.",
        )
        for i in range(min(n, 3))
    ]


def has_key() -> bool:
    return bool(config.parallel_api_key())
