"""Gemini Embedding 2 helpers.

One natively multimodal model. Text, images, audio, and PDFs map into one
3,072-dimension space, so a frame, a line, and a needle-drop are comparable
with one cosine distance.

Gemini Embedding 2 has no task_type parameter. State the job as a text
instruction prefixed to the content. Asymmetric jobs (a short query over
longer documents) prefix only the query side.
"""

from __future__ import annotations

import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Sequence, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from . import config

_T = TypeVar("_T")

# One client per thread, not one shared client. Sharing a single genai.Client
# across a ThreadPoolExecutor throws "client has been closed" once one thread
# tears it down mid-request; thread-local storage gives every worker (and the
# main thread) its own, which is what makes embed_texts below, contradiction
# verification, and per-objective research safe to parallelize.
_local = threading.local()


def client() -> genai.Client:
    c = getattr(_local, "client", None)
    if c is None:
        c = genai.Client()
        _local.client = c
    return c


_MAX_INFLIGHT = 3  # measured against this project's Vertex quota; raise if the quota is
_gate = threading.Semaphore(_MAX_INFLIGHT)  # ever increased, lower if 429s are still frequent


def with_retry(fn: Callable[[], _T], *, attempts: int = 5, base_delay: float = 1.0) -> _T:
    """Every code path that reaches Gemini goes through here. Logical
    parallelism (ThreadPoolExecutor across objectives, contradiction pairs,
    embedding batches) is much wider than the project's actual Vertex quota,
    so a semaphore caps how many requests are ever in flight at once; the
    rest of the threads just wait their turn instead of firing anyway and
    eating a 429. The retry below is the backstop for whatever gets through
    regardless (another tenant on the same quota, a burst on a shared
    project); it never runs while holding the gate, so a slow backoff on one
    thread doesn't stall everyone else queued behind it."""
    for attempt in range(attempts):
        try:
            with _gate:
                return fn()
        except genai_errors.ClientError as e:
            if getattr(e, "code", None) != 429 or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
    raise AssertionError("unreachable")  # loop always returns or raises


# Instruction prefixes for asymmetric retrieval. Prefix the QUERY, leave documents raw.
TASK_SEARCH = "task: search result | query: "
TASK_QA = "task: question answering | query: "
TASK_FACT_CHECK = "task: fact checking | query: "
TASK_CODE = "task: code retrieval | query: "


def _l2_normalize(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed_one(t: str, *, dim: int, prefix: str, normalize: bool) -> list[float]:
    r = with_retry(lambda: client().models.embed_content(
        model=config.EMBED_MODEL,
        contents=(prefix + t) if prefix else t,
        config=types.EmbedContentConfig(output_dimensionality=dim),
    ))
    v = list(r.embeddings[0].values)
    return _l2_normalize(v) if normalize and dim != 3072 else v


def embed_texts(
    texts: Sequence[str],
    *,
    dim: int = 768,
    prefix: str = "",
    normalize: bool = True,
    max_workers: int = 4,
) -> list[list[float]]:
    """Embed a batch of strings. The 3,072 output is pre-normalized; shorter
    cuts are normalized here so every vector is unit length. Batches of more
    than one text embed concurrently; ex.map preserves input order, which
    every caller relies on when zipping results back onto their source items."""
    items = list(texts)
    if len(items) <= 1:
        return [_embed_one(t, dim=dim, prefix=prefix, normalize=normalize) for t in items]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as ex:
        return list(ex.map(
            lambda t: _embed_one(t, dim=dim, prefix=prefix, normalize=normalize), items
        ))


def embed_parts(
    parts: Iterable[types.Part],
    *,
    dim: int = 768,
    normalize: bool = True,
) -> list[float]:
    """Embed one item made of several modalities (for example a still plus its
    caption plus its sound) into a single combined vector."""
    r = with_retry(lambda: client().models.embed_content(
        model=config.EMBED_MODEL,
        contents=list(parts),
        config=types.EmbedContentConfig(output_dimensionality=dim),
    ))
    v = list(r.embeddings[0].values)
    return _l2_normalize(v) if normalize and dim != 3072 else v


def image_part(data: bytes, mime_type: str = "image/png") -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
