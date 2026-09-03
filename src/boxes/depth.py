"""Research depth presets. The same agent, tuned for how hard it digs.

Scout runs in a couple of minutes for a demo. Kubrick is the obsessive setting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Depth:
    name: str
    objectives: int          # size of the initial research plan
    queries_per_objective: int
    extract_urls: int        # how many result URLs to enrich with Parallel Extract
    full_content: bool       # Extract full page text (slow) or objective excerpts (fast)
    images_per_round: int    # pictures to harvest and embed multimodally per round
    docs_per_round: int      # PDFs to harvest and embed per round
    av_per_round: int        # audio + video clips to harvest and embed per round
    max_rounds: int          # autonomous follow-up rounds
    confidence_target: float # stop when research confidence reaches this
    emergent_gaps_per_round: int


SCOUT = Depth("scout", objectives=5, queries_per_objective=1, extract_urls=2,
              full_content=False, images_per_round=4, docs_per_round=2, av_per_round=2,
              max_rounds=2, confidence_target=0.80, emergent_gaps_per_round=1)

PRODUCTION = Depth("production", objectives=10, queries_per_objective=2, extract_urls=4,
                   full_content=True, images_per_round=10, docs_per_round=5, av_per_round=4,
                   max_rounds=3, confidence_target=0.82, emergent_gaps_per_round=2)

KUBRICK = Depth("kubrick", objectives=16, queries_per_objective=3, extract_urls=6,
                full_content=True, images_per_round=20, docs_per_round=10, av_per_round=8,
                max_rounds=6, confidence_target=0.90, emergent_gaps_per_round=3)

PRESETS = {d.name: d for d in (SCOUT, PRODUCTION, KUBRICK)}


def get(name: str) -> Depth:
    return PRESETS.get(name.lower(), SCOUT)
