"""Parallel Search API client.

This is the partner integration for the hackathon Parallel track. The Search API
call sits on the agent's hot path and must run on every research pass.

The exact request and response shape is not pinned here. Confirm against the
Parallel Search API reference, then adjust `search()` and `_parse`. Until a key
is available, `search()` falls back to a clearly labelled stub so the rest of
the pipeline can be built and tested.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from . import config


@dataclass
class SearchHit:
    title: str
    url: str
    text: str
    image_url: str | None = None
    source: str = "parallel"


def _parse(payload: dict) -> list[SearchHit]:
    # TODO: align with the real Parallel Search response schema.
    items = payload.get("results") or payload.get("data") or []
    hits: list[SearchHit] = []
    for it in items:
        hits.append(
            SearchHit(
                title=it.get("title", ""),
                url=it.get("url", ""),
                text=it.get("text") or it.get("snippet") or it.get("content", ""),
                image_url=it.get("image_url") or it.get("image"),
            )
        )
    return hits


def search(query: str, *, max_results: int = 10, timeout: float = 30.0) -> list[SearchHit]:
    key = config.parallel_api_key()
    if not key:
        return _stub(query, max_results)
    resp = httpx.post(
        config.PARALLEL_SEARCH_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query, "max_results": max_results},
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
