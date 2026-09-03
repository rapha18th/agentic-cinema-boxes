"""The reference reel.

Turns the strongest evidence into a sequence of timed beats a filmmaker can read,
each beat carrying its citations. This is a structured plan, not rendered media.
Media rights are the director's call, so every item keeps its source and any
known license note rather than implying free reuse.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from . import llm
from .evidence import Evidence


@dataclass
class ReelBeat:
    t: str            # "00:18"
    title: str        # "Money becoming strange"
    note: str         # what the beat shows
    evidence_ids: list[str]
    citations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


_PROMPT = """You are cutting a reference reel for a film in development.

PREMISE:
{premise}

EVIDENCE (id — citation — snippet):
{catalog}

Group the evidence into 4 to 6 beats that move from establishing the world to its
texture and mood. Return JSON: a list of objects with keys "t" (timecode like
"00:18", starting at "00:00"), "title" (2-4 words), "note" (one sentence),
"evidence_ids" (list of ids that belong in this beat)."""


def build_reel(premise: str, evidence: list[Evidence], *, limit: int = 24) -> list[ReelBeat]:
    pool = evidence[:limit]
    catalog = "\n".join(f"{e.id} — {e.cite()} — {e.text[:140]}" for e in pool)
    raw = llm.generate_json(_PROMPT.format(premise=premise, catalog=catalog))
    by_id = {e.id: e for e in pool}
    beats: list[ReelBeat] = []
    for item in raw if isinstance(raw, list) else raw.get("beats", []):
        ids = [i for i in item.get("evidence_ids", []) if i in by_id]
        beats.append(
            ReelBeat(
                t=str(item.get("t", "00:00")),
                title=str(item.get("title", "")).strip(),
                note=str(item.get("note", "")).strip(),
                evidence_ids=ids,
                citations=[by_id[i].cite() for i in ids],
            )
        )
    return beats
