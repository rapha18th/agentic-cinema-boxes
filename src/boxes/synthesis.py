"""Turn raw evidence into the human-readable narrative for the PDF dossier.

One Gemini call reads the whole research catalog and writes: an overview
that gives a reader who has never seen the project the real picture, and one
plain-prose summary per box. This module writes the connective prose only.
It does not invent facts beyond what the catalog contains, and every summary
sits next to its own source list in the report, so a reader can check the
claim against the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import llm

_STYLE = (
    "Write in plain, spare, declarative sentences. Keep sentences short. "
    "Never use an em dash. Never set one idea against another: no "
    "\"not X, it's Y\", no \"while X, Y\", no \"whereas\", no \"unlike X\", "
    "no \"rather than\", no \"instead of\", no \"X or Y, avoiding Z\". "
    "When you mention prior films, state what each one does on its own line, "
    "plainly, and stop. State each fact on its own, in the order it matters. "
    "The reader has never seen this project before and has nothing else to go on."
)

_PROMPT = """You are writing the human-readable narrative for a film \
research dossier. Someone who has never seen this project should \
understand the world of the film from your words alone.

PREMISE:
{premise}

RESEARCH, box by box, each with a sample of its evidence (citation: snippet):
{catalog}

{prior_art_block}

{style}

Return JSON:
{{"overview": "3 to 5 sentences. What world did the research turn up. What \
this film's angle is within it. If prior art context is given above, name \
in one sentence where this premise sits relative to it.",
 "boxes": {{"<box id>": "3 to 5 sentences synthesizing that box's evidence \
into plain prose a filmmaker can act on. Ground every claim in the \
evidence given. Do not invent details the evidence does not support."}}}}"""


@dataclass
class Narrative:
    overview: str = ""
    box_summaries: dict[str, str] = field(default_factory=dict)


def _catalog(boxes: list[dict], evidence: list[dict], *, per_box: int = 8) -> str:
    by_box: dict[str, list[dict]] = {}
    for e in evidence:
        by_box.setdefault(e.get("objective_id") or "", []).append(e)
    lines: list[str] = []
    for b in boxes:
        bid = b.get("id", "")
        lines.append(f"### {bid} — {b.get('name', '')}")
        if b.get("description"):
            lines.append(b["description"])
        for e in by_box.get(bid, [])[:per_box]:
            cite = e.get("title") or e.get("source_domain") or e.get("url") or ""
            snip = (e.get("text") or "").strip().replace("\n", " ")[:160]
            lines.append(f"- {cite}: {snip}")
    return "\n".join(lines)


def _prior_art_block(prior_art: dict | None) -> str:
    if not prior_art or not prior_art.get("neighbors"):
        return ""
    top = prior_art["neighbors"][:3]
    names = "; ".join(f"{n.get('title', '')} ({n.get('year', '')})" for n in top)
    angle = (prior_art.get("unclaimed_angles") or [{}])[0].get("angle", "")
    lines = [
        f"PRIOR ART CONTEXT: {prior_art.get('surveyed', 0)} existing films "
        "were surveyed for a similar premise.",
    ]
    if names:
        lines.append(f"Closest: {names}.")
    if angle:
        lines.append(f"An angle none of them take: {angle}")
    return "\n".join(lines)


def build(
    premise: str, boxes: list[dict], evidence: list[dict],
    prior_art: dict | None = None,
) -> Narrative:
    if not boxes:
        return Narrative()
    prompt = _PROMPT.format(
        premise=premise,
        catalog=_catalog(boxes, evidence),
        prior_art_block=_prior_art_block(prior_art),
        style=_STYLE,
    )
    raw = llm.generate_json(prompt)
    raw = raw if isinstance(raw, dict) else {}
    return Narrative(
        overview=str(raw.get("overview", "")).strip(),
        box_summaries={
            str(k): str(v).strip() for k, v in (raw.get("boxes") or {}).items()
        },
    )
