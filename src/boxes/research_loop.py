"""The autonomous research loop.

plan -> for each objective: Parallel search + extract -> embed evidence ->
measure coverage per objective and overall research confidence -> find
contradictions (embedding candidates, Gemini verdicts) -> hypothesise the next
gap, including emergent boxes the evidence keeps pointing at -> repeat until
confidence hits the target or the objectives are all covered.

Every step emits an event so a UI can show the agent working. The loop also
builds a research ledger and can stop on its own.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import contradiction, coverage, ontology
from . import parallel_search as ps
from .depth import Depth, get as get_depth
from .embeddings import embed_texts
from .evidence import Evidence
from .ledger import Ledger, RoundRecord
from .ontology import Objective

EventFn = Callable[[dict], None]


def _noop(_: dict) -> None:
    pass


@dataclass
class ResearchProject:
    premise: str
    depth: Depth
    objectives: list[Objective] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    vectors: np.ndarray | None = None
    contradictions: list[contradiction.Verdict] = field(default_factory=list)
    reports: list[coverage.CoverageReport] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)

    @property
    def confidence(self) -> float:
        return self.reports[-1].confidence if self.reports else 0.0

    def _add_evidence(self, items: list[Evidence]) -> int:
        seen = {x.id for x in self.evidence}
        fresh = [e for e in items if e.id not in seen]
        if not fresh:
            return 0
        # images carry their own picture+caption vector; text is batch-embedded
        need = [e for e in fresh if e.vector is None]
        if need:
            got = embed_texts([e.text for e in need], dim=768)
            for e, v in zip(need, got):
                e.vector = v
        vecs = np.asarray([e.vector for e in fresh], dtype=np.float32)
        self.vectors = vecs if self.vectors is None else np.vstack([self.vectors, vecs])
        self.evidence.extend(fresh)
        return len(fresh)

    def signal_terms(self, top: int = 12) -> list[str]:
        """Frequent capitalised phrases across evidence, a rough read on what the
        corpus keeps mentioning. Feeds emergent-gap detection."""
        words = Counter()
        for e in self.evidence:
            for tok in e.text.replace("\n", " ").split():
                t = tok.strip(".,;:()[]\"'").strip()
                if len(t) > 3 and t[0].isupper() and t.lower() not in _STOP:
                    words[t] += 1
        return [w for w, _ in words.most_common(top)]


_STOP = {"this", "that", "there", "these", "those", "which", "while", "after",
         "before", "their", "would", "could", "vienna", "austrian", "austria"}


def run(premise: str, *, depth: str | Depth = "scout", on_event: EventFn = _noop) -> ResearchProject:
    d = depth if isinstance(depth, Depth) else get_depth(depth)
    proj = ResearchProject(premise=premise, depth=d)

    # --- plan -------------------------------------------------------------- #
    proj.objectives = ontology.research_plan(premise, n=d.objectives)
    on_event({"type": "plan", "objectives": [o.to_dict() for o in proj.objectives]})

    # --- round 0: sweep every objective ---------------------------------- #
    _do_round(proj, proj.objectives, run_no=0, on_event=on_event)

    # --- autonomous follow-up rounds ------------------------------------- #
    rounds_done = 0
    while True:
        rep = proj.reports[-1]
        stop, why = coverage.should_stop(rep, d.confidence_target, rounds_done, d.max_rounds)
        if stop:
            on_event({"type": "stop", "reason": why, "confidence": rep.confidence})
            break
        rounds_done += 1

        thin_ids = {c.id for c in coverage.thinnest(rep, k=2)}
        targets: list[Objective] = [o for o in proj.objectives if o.id in thin_ids]
        emergent = ontology.emergent_objective(
            premise, proj.objectives, proj.signal_terms(), next_index=len(proj.objectives) + 1
        )
        if emergent and len(proj.ledger.rounds) and emergent.name not in {
            o.name for o in proj.objectives
        }:
            proj.objectives.append(emergent)
            targets.append(emergent)
            on_event({"type": "emergent_gap", "objective": emergent.to_dict()})

        _do_round(proj, targets, run_no=rounds_done, on_event=on_event, emergent=emergent)

    return proj


def _do_round(
    proj: ResearchProject,
    targets: list[Objective],
    *,
    run_no: int,
    on_event: EventFn,
    emergent: Objective | None = None,
) -> None:
    d = proj.depth
    before = proj.reports[-1] if proj.reports else None
    rec = RoundRecord(
        run=run_no,
        coverage_before=before.overall_coverage if before else 0.0,
        confidence_before=before.confidence if before else 0.0,
    )

    per_obj_images = max(1, d.images_per_round // max(1, len(targets))) if d.images_per_round else 0
    for obj in targets:
        queries = ontology.objective_queries(obj, proj.premise, k=d.queries_per_objective)
        on_event({"type": "search", "objective": obj.name, "queries": queries})
        rec.searches.append({"objective": obj.name, "queries": queries})
        found = ps.research(
            obj.description or obj.name,
            queries,
            objective_id=obj.id,
            extract_urls=d.extract_urls,
            full_content=d.full_content,
            round_no=run_no,
            harvest_images_limit=per_obj_images,
        )
        n_img = sum(1 for e in found if e.modality == "image")
        on_event({"type": "extract", "objective": obj.name, "sources": len(found) - n_img, "images": n_img})
        added = proj._add_evidence(found)
        rec.sources_examined += len(found) - n_img
        rec.evidence_indexed += added
        rec.images_indexed += n_img
        rec.sources_extracted += min(d.extract_urls, max(0, len(found) - n_img))
        if obj.emergent:
            rec.new_boxes.append(obj.name)

    # --- contradictions: candidates by embedding, verdicts by Gemini --- #
    max_checks = 8 if proj.depth.name == "scout" else 18
    new_verdicts = contradiction.find_contradictions(proj.evidence, proj.vectors, max_checks=max_checks)
    for v in new_verdicts:
        if all((v.a_id, v.b_id) != (x.a_id, x.b_id) for x in proj.contradictions):
            proj.contradictions.append(v)
            if v.relation == "contradicts":
                rec.conflicts.append(f"{v.a_cite}  vs  {v.b_cite}")
                on_event({"type": "contradiction", "verdict": v.to_dict()})

    # Only genuine contradictions count against confidence. "contextualises"
    # verdicts are reconciled differences and do not.
    open_conflicts = sum(1 for v in proj.contradictions if v.relation == "contradicts")

    # --- coverage + confidence ---------------------------------------- #
    rep = coverage.build_report(
        proj.objectives, proj.evidence, proj.vectors,
        unresolved_contradictions=open_conflicts,
    )
    proj.reports.append(rep)
    rec.coverage_after = rep.overall_coverage
    rec.confidence_after = rep.confidence
    on_event({"type": "coverage", "report": rep.to_dict(), "summary": rep.summary()})

    thin = coverage.thinnest(rep, 1)
    rec.next_action = (
        f"investigate {thin[0].name} (score {thin[0].score:.2f})" if thin else "review contradictions"
    )
    proj.ledger.add(rec)
    on_event({"type": "round_done", "record": rec.to_dict()})
