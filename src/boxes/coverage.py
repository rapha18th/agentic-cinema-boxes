"""Coverage and research completeness.

Coverage is measured per research objective, never against empty regions of
embedding space. For each objective: how much evidence supports it, how diverse
the sources are. Research completeness rolls those up with source diversity,
provenance quality, and a penalty for unresolved contradictions, and gives the
loop a real stopping criterion.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict

import numpy as np

from .embeddings import embed_texts, TASK_SEARCH
from .evidence import Evidence
from .ontology import Objective

_TARGET_EVIDENCE = 8      # evidence items for an objective to count as covered
_TARGET_DOMAINS = 4       # distinct source domains for full diversity credit


@dataclass
class ObjectiveCoverage:
    id: str
    name: str
    evidence_count: int
    distinct_domains: int
    score: float           # 0..1
    quality: float
    thinnest_terms: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CoverageReport:
    per_objective: list[ObjectiveCoverage]
    overall_coverage: float
    source_diversity: float
    provenance_quality: float
    unresolved_contradictions: int
    confidence: float

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def summary(self) -> str:
        return (
            f"readiness {self.confidence:.0%} | coverage {self.overall_coverage:.0%} | "
            f"diversity {self.source_diversity:.0%} | provenance {self.provenance_quality:.0%} | "
            f"open contradictions {self.unresolved_contradictions}"
        )


def _assign(evidence: list[Evidence], ev_vectors: np.ndarray, obj_vectors: np.ndarray) -> list[int]:
    """Nearest objective for each evidence item."""
    if len(evidence) == 0:
        return []
    e = ev_vectors / (np.linalg.norm(ev_vectors, axis=1, keepdims=True) + 1e-9)
    o = obj_vectors / (np.linalg.norm(obj_vectors, axis=1, keepdims=True) + 1e-9)
    return list(np.argmax(e @ o.T, axis=1))


def build_report(
    objectives: list[Objective],
    evidence: list[Evidence],
    ev_vectors: np.ndarray,
    *,
    unresolved_contradictions: int = 0,
) -> CoverageReport:
    obj_vectors = np.asarray(
        embed_texts([f"{o.name}. {o.description}" for o in objectives], dim=768, prefix=TASK_SEARCH),
        dtype=np.float32,
    )
    assign = _assign(evidence, ev_vectors, obj_vectors) if len(evidence) else []

    per: list[ObjectiveCoverage] = []
    for oi, obj in enumerate(objectives):
        mine = [evidence[k] for k, a in enumerate(assign) if a == oi]
        domains = Counter(e.source_domain for e in mine if e.source_domain)
        n, d = len(mine), len(domains)
        quality = float(np.mean([e.quality_score for e in mine])) if mine else 0.0
        score = (
            0.48 * min(1.0, n / _TARGET_EVIDENCE)
            + 0.34 * min(1.0, d / _TARGET_DOMAINS)
            + 0.18 * quality
        )
        per.append(
            ObjectiveCoverage(
                id=obj.id,
                name=obj.name,
                evidence_count=n,
                distinct_domains=d,
                score=round(score, 3),
                quality=round(quality, 3),
                thinnest_terms=[],
            )
        )

    overall = float(np.mean([p.score for p in per])) if per else 0.0

    all_domains = {e.source_domain for e in evidence if e.source_domain}
    diversity = min(1.0, len(all_domains) / max(1, 0.5 * len(evidence))) if evidence else 0.0

    provenance = float(np.mean([e.quality_score for e in evidence])) if evidence else 0.0

    penalty = min(0.25, 0.05 * unresolved_contradictions)
    confidence = max(
        0.0,
        min(1.0, 0.62 * overall + 0.18 * diversity + 0.12 * provenance + 0.04 - penalty),
    )

    return CoverageReport(
        per_objective=per,
        overall_coverage=round(overall, 3),
        source_diversity=round(diversity, 3),
        provenance_quality=round(provenance, 3),
        unresolved_contradictions=unresolved_contradictions,
        confidence=round(confidence, 3),
    )


def thinnest(report: CoverageReport, k: int = 2) -> list[ObjectiveCoverage]:
    return sorted(report.per_objective, key=lambda p: p.score)[:k]


def should_stop(report: CoverageReport, target: float, rounds_done: int, max_rounds: int) -> tuple[bool, str]:
    # Always run at least one autonomous follow-up round. Opening its own boxes is
    # the point of the tool, so it never stops straight after the first sweep.
    if rounds_done < 1:
        return False, ""
    if report.confidence >= target:
        return True, f"research completeness {report.confidence:.0%} reached target {target:.0%}"
    if rounds_done >= max_rounds:
        return True, f"max rounds ({max_rounds}) reached at {report.confidence:.0%} completeness"
    thin = thinnest(report, 1)
    if thin and thin[0].score >= 0.8:
        return True, "every objective is well covered"
    return False, ""
