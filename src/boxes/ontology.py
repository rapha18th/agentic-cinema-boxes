"""The research ontology.

Coverage only means something against an explicit plan. Given a premise, Gemini
writes a list of research objectives. Each objective is one box. Coverage is then
measured per objective, not against empty regions of embedding space.

The ontology is not fixed. `emergent_objective` looks at what the evidence keeps
mentioning that has no box yet, and proposes one.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

from . import llm

# Fixed vocabulary so the dashboard and report can filter on it. A box can
# serve more than one department (a "STREET FASHION" box feeds both costume
# and art direction).
DEPARTMENTS = ["script", "casting", "costume", "art_direction", "sound",
               "cinematography", "locations"]


@dataclass
class Objective:
    id: str
    name: str          # short box label, e.g. "BANKING INTERIORS"
    description: str    # what counts as evidence for this box
    rationale: str = "" # why this matters to the film
    emergent: bool = False
    departments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_DEPT_LIST = ", ".join(DEPARTMENTS)
_PLAN_PROMPT = """You are the research director for a film in development.

PREMISE:
{premise}

Write a research plan as {n} objectives. Each objective is one "box" of research
the production needs before it can build this world. Cover the concrete texture of
the setting: money, institutions, architecture, streets, transport, work, class,
politics, policing, crime, fashion, food, language, technology, media, sound,
interiors, daily life. Bias toward what this specific premise needs.

Return JSON: a list of objects with keys "name" (2-4 words, uppercase),
"description" (one sentence: what evidence answers this box), "rationale"
(one sentence: why the film needs it), "departments" (1-3 values from this
fixed list, whichever production departments this box's evidence would
actually brief: {depts})."""


def _clean_departments(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [d for d in (str(x).strip().lower() for x in raw) if d in DEPARTMENTS]


def research_plan(premise: str, n: int = 10) -> list[Objective]:
    raw = llm.generate_json(_PLAN_PROMPT.format(premise=premise, n=n, depts=_DEPT_LIST))
    out: list[Objective] = []
    for i, item in enumerate(raw if isinstance(raw, list) else raw.get("objectives", [])):
        name = str(item.get("name", f"BOX {i + 1}")).strip().upper()
        out.append(
            Objective(
                id=f"obj{i + 1:02d}",
                name=name,
                description=str(item.get("description", "")).strip(),
                rationale=str(item.get("rationale", "")).strip(),
                departments=_clean_departments(item.get("departments")),
            )
        )
    return out[:n]


_QUERIES_PROMPT = """Film premise: {premise}

Research boxes needing search queries:
{catalog}

For EACH box, write {k} web search queries that would find primary and
documentary evidence for it. Return JSON: an object keyed by box id, each
value a list of {k} query strings. Example: {{"obj01": ["query one", "query two"]}}"""


def objective_queries_batch(
    objs: list[Objective], premise: str, k: int = 2
) -> dict[str, list[str]]:
    """One call writes queries for every target box in a round, instead of one
    call per box — the same batched-catalog pattern research_plan and the reel
    already use."""
    if not objs:
        return {}
    catalog = "\n".join(f"- {o.id}: {o.name} — {o.description}" for o in objs)
    raw = llm.generate_json(_QUERIES_PROMPT.format(premise=premise, catalog=catalog, k=k))
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, list[str]] = {}
    for o in objs:
        qs = raw.get(o.id) or []
        out[o.id] = [str(q).strip() for q in qs][:k] or [f"{o.name.lower()} {premise}"]
    return out


_EMERGENT_PROMPT = """Film premise:
{premise}

Existing research boxes:
{boxes}

Concepts that keep appearing across the evidence collected so far:
{signals}

Is there a concept that clearly deserves its own box but does not have one yet?
It must be specific, recurring, and cross-cutting (it should touch several
existing boxes). If yes, return JSON:
{{"found": true, "name": "NEW BOX NAME", "description": "one sentence",
  "rationale": "one sentence on why it cuts across the others",
  "departments": "1-3 values from {depts}"}}
If nothing qualifies, return {{"found": false}}."""


def emergent_objective(
    premise: str, objectives: list[Objective], signal_terms: list[str], next_index: int
) -> Objective | None:
    boxes = "\n".join(f"- {o.name}: {o.description}" for o in objectives)
    signals = ", ".join(signal_terms) or "(none)"
    raw = llm.generate_json(
        _EMERGENT_PROMPT.format(premise=premise, boxes=boxes, signals=signals, depts=_DEPT_LIST)
    )
    if not isinstance(raw, dict) or not raw.get("found"):
        return None
    return Objective(
        id=f"obj{next_index:02d}",
        name=str(raw.get("name", "EMERGENT BOX")).strip().upper(),
        description=str(raw.get("description", "")).strip(),
        rationale=str(raw.get("rationale", "")).strip(),
        emergent=True,
        departments=_clean_departments(raw.get("departments")),
    )
