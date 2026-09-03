"""The ADK agent for THE BOXES.

`root_agent` runs on Gemini 3.8 Flash (GA 2 September 2026, id `gemini-3.8-flash`,
built for agentic multi-step reasoning). It is the reasoning surface over the
autonomous research loop: it can plan, launch a research run, read coverage and
confidence, list verified contradictions, answer from the index with citations,
and cut a reference reel.
"""

from __future__ import annotations

import numpy as np

from google.adk.agents import Agent

from . import config, reel
from . import research_loop as rl
from .embeddings import embed_texts, TASK_SEARCH
from .ontology import research_plan

_PROJECT: rl.ResearchProject | None = None


def plan_research(premise: str, objectives: int = 8) -> dict:
    """Draft the research plan for a premise without searching yet.

    Args:
        premise: The film premise.
        objectives: How many research boxes to plan (5-16).

    Returns:
        The list of planned boxes with their descriptions.
    """
    plan = research_plan(premise, n=objectives)
    return {"boxes": [o.to_dict() for o in plan]}


def run_research(premise: str, depth: str = "scout") -> dict:
    """Run the autonomous research loop: plan, search and extract through Parallel,
    embed evidence, measure coverage and confidence, verify contradictions, and
    open follow-up boxes on its own until confidence hits the target.

    Args:
        premise: The film premise.
        depth: "scout" (fast, for a demo), "production", or "kubrick" (obsessive).

    Returns:
        The research ledger, final coverage and confidence, box list, and counts.
    """
    global _PROJECT
    _PROJECT = rl.run(premise, depth=depth)
    p = _PROJECT
    rep = p.reports[-1]
    return {
        "ledger": p.ledger.render(),
        "confidence": rep.confidence,
        "coverage": rep.overall_coverage,
        "summary": rep.summary(),
        "boxes": [
            {"name": o.name, "emergent": o.emergent,
             "score": next((c.score for c in rep.per_objective if c.id == o.id), 0.0)}
            for o in p.objectives
        ],
        "evidence_count": len(p.evidence),
        "verified_contradictions": len(p.contradictions),
    }


def coverage_report() -> dict:
    """Current coverage per box and overall research confidence."""
    if not _PROJECT or not _PROJECT.reports:
        return {"error": "no research run yet; call run_research first"}
    rep = _PROJECT.reports[-1]
    return {
        "summary": rep.summary(),
        "confidence": rep.confidence,
        "per_box": [c.to_dict() for c in sorted(rep.per_objective, key=lambda c: c.score)],
    }


def list_contradictions() -> dict:
    """Verified contradiction and context verdicts. Candidates come from embedding
    similarity; the relation is checked by Gemini, not assumed from distance."""
    if not _PROJECT:
        return {"error": "no research run yet"}
    return {
        "verdicts": [
            {"relation": v.relation, "explanation": v.explanation,
             "a": v.a_cite, "b": v.b_cite, "similarity": v.similarity}
            for v in _PROJECT.contradictions
        ]
    }


def query_index(question: str, k: int = 6) -> dict:
    """Answer a question from the research index, returning the passages and their
    citations. Answer only from what comes back.

    Args:
        question: A question about the film's world.
        k: How many passages to retrieve.
    """
    if not _PROJECT or _PROJECT.vectors is None:
        return {"error": "no research run yet; call run_research first"}
    qv = np.asarray(embed_texts([question], dim=768, prefix=TASK_SEARCH)[0], dtype=np.float32)
    v = _PROJECT.vectors / (np.linalg.norm(_PROJECT.vectors, axis=1, keepdims=True) + 1e-9)
    sims = v @ (qv / (np.linalg.norm(qv) + 1e-9))
    order = np.argsort(-sims)[:k]
    return {
        "matches": [
            {"score": round(float(sims[i]), 3),
             "text": _PROJECT.evidence[i].text[:600],
             "citation": _PROJECT.evidence[i].cite(),
             "url": _PROJECT.evidence[i].url}
            for i in order
        ]
    }


def build_reference_reel() -> dict:
    """Cut a reference reel from the strongest evidence: timed beats, each with
    citations. A plan, not rendered media."""
    if not _PROJECT or not _PROJECT.evidence:
        return {"error": "no research run yet"}
    beats = reel.build_reel(_PROJECT.premise, _PROJECT.evidence)
    return {"beats": [b.to_dict() for b in beats]}


root_agent = Agent(
    model=config.CHAT_MODEL,
    name="boxes",
    description="Autonomous multimodal research department for filmmakers.",
    instruction=(
        "You are THE BOXES. Given a film premise, run_research to build the world: "
        "it plans research boxes, searches and extracts through Parallel, embeds "
        "evidence with Gemini Embedding 2, scores coverage per box, verifies "
        "contradictions, and opens its own follow-up boxes until confident. "
        "After a run, use coverage_report, list_contradictions, query_index, and "
        "build_reference_reel. Always answer from query_index results and cite the "
        "source for every claim. Keep replies concrete and terse."
    ),
    tools=[
        plan_research,
        run_research,
        coverage_report,
        list_contradictions,
        query_index,
        build_reference_reel,
    ],
)


def project() -> rl.ResearchProject | None:
    return _PROJECT
