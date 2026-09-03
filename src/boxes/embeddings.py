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
from typing import Iterable, Sequence

from google import genai
from google.genai import types

from . import config

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


# Instruction prefixes for asymmetric retrieval. Prefix the QUERY, leave documents raw.
TASK_SEARCH = "task: search result | query: "
TASK_QA = "task: question answering | query: "
TASK_FACT_CHECK = "task: fact checking | query: "
TASK_CODE = "task: code retrieval | query: "


def _l2_normalize(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed_texts(
    texts: Sequence[str],
    *,
    dim: int = 768,
    prefix: str = "",
    normalize: bool = True,
) -> list[list[float]]:
    """Embed a batch of strings. The 3,072 output is pre-normalized; shorter
    cuts are normalized here so every vector is unit length."""
    out: list[list[float]] = []
    for t in list(texts):
        r = client().models.embed_content(
            model=config.EMBED_MODEL,
            contents=(prefix + t) if prefix else t,
            config=types.EmbedContentConfig(output_dimensionality=dim),
        )
        v = list(r.embeddings[0].values)
        out.append(_l2_normalize(v) if normalize and dim != 3072 else v)
    return out


def embed_parts(
    parts: Iterable[types.Part],
    *,
    dim: int = 768,
    normalize: bool = True,
) -> list[float]:
    """Embed one item made of several modalities (for example a still plus its
    caption plus its sound) into a single combined vector."""
    r = client().models.embed_content(
        model=config.EMBED_MODEL,
        contents=list(parts),
        config=types.EmbedContentConfig(output_dimensionality=dim),
    )
    v = list(r.embeddings[0].values)
    return _l2_normalize(v) if normalize and dim != 3072 else v


def image_part(data: bytes, mime_type: str = "image/png") -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
