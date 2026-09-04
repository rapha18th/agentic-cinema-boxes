"""Two-stage contradiction detection.

Stage 1: embedding similarity finds pairs of evidence that talk about the same
thing. Similarity alone never proves disagreement, so this only produces
candidates. It bands the score: near-duplicates and unrelated pairs are skipped.

Stage 2: Gemini reads both fragments and classifies the relationship as
supports / contradicts / contextualises / unrelated, with an explanation and the
two citations.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

import numpy as np

from . import llm
from .evidence import Evidence

RELATIONS = ("supports", "contradicts", "contextualises", "unrelated")


@dataclass
class Verdict:
    a_id: str
    b_id: str
    relation: str
    explanation: str
    a_cite: str
    b_cite: str
    similarity: float

    def to_dict(self) -> dict:
        return asdict(self)


def candidate_pairs(
    vectors: np.ndarray,
    *,
    low: float = 0.58,
    high: float = 0.88,
    max_pairs: int = 40,
) -> list[tuple[int, int, float]]:
    """Index pairs whose cosine similarity sits in the band: related enough to be
    about the same subject, not so close they are the same passage."""
    if vectors is None or len(vectors) < 2:
        return []
    v = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
    sims = v @ v.T
    iu = np.triu_indices(len(v), k=1)
    pairs = [
        (int(i), int(j), float(sims[i, j]))
        for i, j in zip(*iu)
        if low <= sims[i, j] <= high
    ]
    pairs.sort(key=lambda p: -p[2])
    return pairs[:max_pairs]


_VERIFY_PROMPT = """Two pieces of research evidence about the same film's world.

A ({a_cite}):
{a_text}

B ({b_cite}):
{b_text}

Classify the relationship of B to A as exactly one of:
supports, contradicts, contextualises, unrelated.

"contradicts" means they make claims that cannot both be true. "contextualises"
means they differ but are reconcilable (different time, place, or scope).

Return JSON: {{"relation": "...", "explanation": "one or two sentences"}}"""


def verify(a: Evidence, b: Evidence, similarity: float) -> Verdict:
    raw = llm.generate_json(
        _VERIFY_PROMPT.format(
            a_cite=a.cite(), a_text=a.text[:900], b_cite=b.cite(), b_text=b.text[:900]
        )
    )
    rel = str(raw.get("relation", "unrelated")).strip().lower()
    if rel not in RELATIONS:
        rel = "unrelated"
    return Verdict(
        a_id=a.id,
        b_id=b.id,
        relation=rel,
        explanation=str(raw.get("explanation", "")).strip(),
        a_cite=a.cite(),
        b_cite=b.cite(),
        similarity=round(similarity, 3),
    )


def find_contradictions(
    evidence: list[Evidence],
    vectors: np.ndarray,
    *,
    max_checks: int = 24,
    max_workers: int = 4,
) -> list[Verdict]:
    """Run both stages. Returns only the verified contradicts / contextualises
    verdicts, most similar first. Each pair's Gemini verdict is independent of
    every other, so they verify concurrently rather than one at a time."""
    pairs = candidate_pairs(vectors, max_pairs=max_checks)
    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(pairs))) as ex:
        results = list(ex.map(lambda p: verify(evidence[p[0]], evidence[p[1]], p[2]), pairs))
    return [v for v in results if v.relation in ("contradicts", "contextualises")]
