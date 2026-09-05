"""Run THE BOXES end to end and freeze the result as the public demo snapshot.

    python scripts/snapshot_demo.py scout    "A premise ..."
    python scripts/snapshot_demo.py production "A premise ..."

Writes web/src/demo/snapshot.json: the same shapes the live workspace renders,
so the read-only /demo page is a genuine run, not hand-authored copy.
"""

from __future__ import annotations

import builtins
import functools
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
print = functools.partial(builtins.print, flush=True)

from boxes import prior_art as prior_art_mod  # noqa: E402
from boxes import reel as reel_mod  # noqa: E402
from boxes import research_loop as rl  # noqa: E402
from boxes import synthesis as synthesis_mod  # noqa: E402

DEFAULT_PREMISE = "A period drama set at MIT in 1966, the year Joseph Weizenbaum built ELIZA."
OUT = ROOT / "web" / "public" / "demo-snapshot.json"

# Sources worth surfacing a contradiction between. A disagreement between two
# low-authority pages is noise, not a research finding.
_CREDIBLE = (
    ".gov", ".edu", ".ac.uk", "wikipedia.org", "archive.org", "loc.gov",
    "si.edu", "computerhistory.org", "multicians.org", "ieee.org", "jstor.org",
    "nature.com", "acm.org", "bitsavers.org", "britannica.com", "nasa.gov",
    "smithsonianmag.com", "hathitrust.org", "mit.edu",
)
# Pages that pollute a 20th-century history run (wrong institution, listicles).
_JUNK_DOMAINS = (
    "instagram.com", "shiksha.com", "careers360.com", "collegedunia.com",
    "quora.com", "pinterest.", "facebook.com", "tiktok.com",
)


def _credible(domain: str) -> bool:
    d = (domain or "").lower()
    return any(tok in d for tok in _CREDIBLE)


def _junk(domain: str) -> bool:
    d = (domain or "").lower()
    return any(tok in d for tok in _JUNK_DOMAINS)


def _fallback_title(premise: str) -> str:
    """A short slate name when none is passed. Prefers a proper noun plus a year."""
    year = next((w for w in premise.replace(".", " ").split() if w.isdigit() and len(w) == 4), "")
    caps = [w.strip(".,") for w in premise.split() if w[:1].isupper() and w.strip(".,").isalpha()]
    skip = {"A", "An", "The", "In", "At"}
    name = next((w for w in caps if w not in skip), "")
    if name and year:
        return f"{name.upper()} · {year}"
    return (name or premise.split(",")[0][:40]).upper()


def semantic_coordinates(vectors: np.ndarray | None) -> list[tuple[float, float]]:
    if vectors is None or len(vectors) == 0:
        return []
    mat = np.asarray(vectors, dtype=np.float32)
    if len(mat) == 1:
        return [(0.5, 0.5)]
    centered = mat - mat.mean(axis=0, keepdims=True)
    try:
        u, s, _ = np.linalg.svd(centered, full_matrices=False)
        xy = u[:, :2] * s[:2]
    except np.linalg.LinAlgError:
        return [(0.5, 0.5) for _ in range(len(mat))]
    if xy.shape[1] == 1:
        xy = np.column_stack([xy[:, 0], np.zeros(len(xy))])
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    scaled = 0.08 + (xy - lo) / np.maximum(hi - lo, 1e-9) * 0.84
    return [(round(float(x), 5), round(float(y), 5)) for x, y in scaled]


def main() -> None:
    args = sys.argv[1:]
    depth = args[0] if args and args[0] in ("scout", "production", "kubrick") else "scout"
    free = [a for a in args if a not in ("scout", "production", "kubrick")]
    premise = free[0] if free else DEFAULT_PREMISE
    title = free[1] if len(free) > 1 else ""

    rounds: list[dict] = []
    verdicts: list[dict] = []
    emergent: list[str] = []
    stop_box: list[str] = [""]

    def on_event(ev: dict) -> None:
        t = ev.get("type")
        if t == "plan":
            print(f"\nPLAN · {len(ev['objectives'])} boxes")
            for o in ev["objectives"]:
                print(f"  {o['name']:<30} {', '.join(o.get('departments') or [])}")
        elif t == "search":
            print(f"  search  {ev['objective']}")
        elif t == "extract":
            extra = ", ".join(f"{ev[k]} {k}" for k in ("images", "docs", "av") if ev.get(k))
            print(f"  extract {ev['objective']}: {ev['sources']} sources" + (f" + {extra}" if extra else ""))
        elif t == "emergent_gap":
            emergent.append(ev["objective"]["name"])
            print(f"\n  EMERGENT: {ev['objective']['name']} — {ev['objective']['description']}")
        elif t == "coverage":
            print(f"  -> {ev['summary']}")
        elif t == "contradiction":
            verdicts.append(ev["verdict"])
            print(f"  ! {ev['verdict']['relation']}: {ev['verdict']['a_cite']} vs {ev['verdict']['b_cite']}")
        elif t == "round_done":
            rounds.append(ev["record"])
        elif t == "stop":
            stop_box[0] = ev["reason"]
            print(f"\nSTOP: {ev['reason']}")

    t0 = time.time()
    print(f"depth={depth}\npremise: {premise}\n")
    proj = rl.run(premise, depth=depth, on_event=on_event)

    rep = proj.reports[-1]
    cov_by_id = {c["id"]: c for c in rep.to_dict()["per_objective"]}

    print("\nPRIOR ART SURVEY …")
    prior_art = prior_art_mod.survey(premise).to_dict()

    print("REEL …")
    beats = [b.to_dict() for b in reel_mod.build_reel(premise, proj.evidence)]

    print("SYNTHESIS …")
    obj_dicts = [o.to_dict() for o in proj.objectives]
    all_ev = [e.to_dict() for e in proj.evidence]

    coords = semantic_coordinates(proj.vectors)
    for i, e in enumerate(all_ev):
        if i < len(coords):
            e["map_x"], e["map_y"] = coords[i]

    # Drop pages that pollute a period-history run before they reach the demo.
    dropped_ids = {e["id"] for e in all_ev if _junk(e.get("source_domain", ""))}
    ev_dicts = [e for e in all_ev if e["id"] not in dropped_ids]
    kept_ids = {e["id"] for e in ev_dicts}

    # Keep a verdict only when it links two surviving fragments and at least one
    # side is a source worth arguing about.
    cite_by_id = {v["a_id"]: v["a_cite"] for v in verdicts}
    cite_by_id.update({v["b_id"]: v["b_cite"] for v in verdicts})
    dom_by_id = {e["id"]: e.get("source_domain", "") for e in all_ev}
    verdicts = [
        v for v in verdicts
        if v["a_id"] in kept_ids and v["b_id"] in kept_ids
        and (_credible(dom_by_id.get(v["a_id"], "")) or _credible(dom_by_id.get(v["b_id"], "")))
    ]

    narrative = synthesis_mod.build(premise, obj_dicts, ev_dicts, prior_art)
    if dropped_ids:
        print(f"  dropped {len(dropped_ids)} off-topic fragments, "
              f"{len([v for v in verdicts])} verdicts kept")

    boxes = []
    for o in obj_dicts:
        c = cov_by_id.get(o["id"], {})
        mine = [e for e in ev_dicts if e.get("objective_id") == o["id"]]
        boxes.append({
            **o,
            "score": c.get("score", 0.0),
            "quality": c.get("quality", 0.0),
            "evidence_count": len(mine),
            "distinct_domains": len({e.get("source_domain") for e in mine if e.get("source_domain")}),
            "summary": narrative.box_summaries.get(o["id"], ""),
        })

    by_mod: dict[str, int] = {}
    for e in ev_dicts:
        by_mod[e.get("modality", "text")] = by_mod.get(e.get("modality", "text"), 0) + 1

    open_contradictions = sum(1 for v in verdicts if v["relation"] == "contradicts")

    snapshot = {
        "premise": premise,
        "title": title or _fallback_title(premise),
        "depth": depth,
        "generated_at": time.time(),
        "elapsed_seconds": round(time.time() - t0, 1),
        "stop_reason": stop_box[0],
        "confidence": rep.confidence,
        "coverage": rep.overall_coverage,
        "source_diversity": rep.source_diversity,
        "provenance_quality": rep.provenance_quality,
        "unresolved_contradictions": open_contradictions,
        "overview": narrative.overview,
        "boxes": boxes,
        "evidence": ev_dicts,
        "runs": rounds,
        "verdicts": verdicts,
        "prior_art": prior_art,
        "reel": beats,
        "modality_counts": by_mod,
        "emergent_boxes": emergent,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size // 1024} KB)")
    print(f"elapsed {snapshot['elapsed_seconds']}s")
    print(f"boxes {len(boxes)}  ({len(emergent)} emergent: {', '.join(emergent) or 'none'})")
    print(f"evidence {len(ev_dicts)}  modality {by_mod}")
    print(f"contradictions {len(verdicts)}")
    print(f"readiness {rep.confidence:.0%}  coverage {rep.overall_coverage:.0%}")
    print(f"prior art: {prior_art.get('surveyed', 0)} surveyed, "
          f"{len(prior_art.get('neighbors', []))} neighbors, "
          f"{len(prior_art.get('unclaimed_angles', []))} angles")
    print(f"reel beats {len(beats)}")


if __name__ == "__main__":
    main()
