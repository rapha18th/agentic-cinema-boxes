"""Freeze an existing Firestore research run as a static /demo snapshot.

    python scripts/freeze_project.py <uid> <pid> --slug chitepo --title "CHITEPO · 1975"

Reads a finished project straight from Firestore (Admin SDK, application-default
credentials), curates it down to a demo-sized evidence set, recomputes the map
projection over the kept fragments, and writes:

    web/public/demo-<slug>.json
    web/public/demo-<slug>-dossier.pdf

Same shapes the read-only workspace renders, so the second demo is a real
Kubrick-depth run, not hand-authored copy.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "service"))

import firebase_admin
from firebase_admin import firestore

from snapshot_demo import _CREDIBLE, _JUNK_DOMAINS, _credible, _fallback_title, semantic_coordinates

PROJECT_ID = "helenia-11f98"
PER_BOX_TEXT = 9  # strongest text fragments to keep per research box


def _has(domain: str, toks) -> bool:
    d = (domain or "").lower()
    return any(t in d for t in toks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("uid")
    ap.add_argument("pid")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--stop", default="")
    a = ap.parse_args()

    firebase_admin.initialize_app(options={"projectId": PROJECT_ID})
    db = firestore.client()
    ref = db.collection("users").document(a.uid).collection("projects").document(a.pid)

    p = ref.get().to_dict()
    if not p:
        sys.exit(f"no project {a.pid} under {a.uid}")

    boxes = [d.to_dict() for d in ref.collection("boxes").stream()]
    evidence = [d.to_dict() for d in ref.collection("evidence").stream()]
    runs = sorted((d.to_dict() for d in ref.collection("runs").stream()), key=lambda r: r.get("run", 0))
    verdicts = [d.to_dict() for d in ref.collection("verdicts").stream()]
    reel = (ref.collection("meta").document("reel").get().to_dict() or {}).get("beats", [])
    prior_art = ref.collection("meta").document("prior_art").get().to_dict() or {}
    vecs = {d.id: d.to_dict().get("vector768") for d in ref.collection("vectors").stream()}

    print(f"pulled: {len(boxes)} boxes, {len(evidence)} evidence, {len(runs)} runs, "
          f"{len(verdicts)} verdicts, {len(reel)} reel beats, {len(vecs)} vectors")

    # --- curate the evidence set to demo size ------------------------------- #
    by_id = {e["id"]: e for e in evidence}
    keep: set[str] = set()

    # every media fragment (this is a multimodal index; show it)
    keep |= {e["id"] for e in evidence if (e.get("modality") or "text") != "text"}
    # both sides of every verdict
    for v in verdicts:
        keep |= {v.get("a_id"), v.get("b_id")}
    # everything a reel beat cites
    for b in reel:
        keep |= set(b.get("evidence_ids") or [])
    # strongest text per box
    for box in boxes:
        mine = sorted(
            (e for e in evidence
             if e.get("objective_id") == box["id"] and (e.get("modality") or "text") == "text"),
            key=lambda e: e.get("quality_score", 0.0), reverse=True,
        )
        keep |= {e["id"] for e in mine[:PER_BOX_TEXT]}

    keep.discard(None)
    keep -= {e["id"] for e in evidence if _has(e.get("source_domain", ""), _JUNK_DOMAINS)}
    kept = [by_id[i] for i in keep if i in by_id]

    # --- recompute the map projection over the kept fragments -------------- #
    ordered = [e for e in kept if vecs.get(e["id"])]
    mat = np.asarray([vecs[e["id"]] for e in ordered], dtype=np.float32)
    coords = semantic_coordinates(mat) if len(mat) else []
    for e, (x, y) in zip(ordered, coords):
        e["map_x"], e["map_y"] = x, y
    kept.sort(key=lambda e: (e.get("objective_id") or "", -e.get("quality_score", 0.0)))

    # --- verdicts that still link two kept fragments ---------------------- #
    dom = {e["id"]: e.get("source_domain", "") for e in evidence}
    kept_ids = {e["id"] for e in kept}
    verdicts = [
        v for v in verdicts
        if v.get("a_id") in kept_ids and v.get("b_id") in kept_ids
        and (_credible(dom.get(v.get("a_id"), "")) or _credible(dom.get(v.get("b_id"), "")))
    ]
    open_contra = sum(1 for v in verdicts if v.get("relation") == "contradicts")

    # --- box counts over the kept set ----------------------------------- #
    for box in boxes:
        mine = [e for e in kept if e.get("objective_id") == box["id"]]
        box["evidence_count"] = len(mine)
        box["distinct_domains"] = len({e.get("source_domain") for e in mine if e.get("source_domain")})

    mods: dict[str, int] = {}
    for e in kept:
        mods[e.get("modality", "text")] = mods.get(e.get("modality", "text"), 0) + 1

    snapshot = {
        "premise": p.get("premise", ""),
        "title": a.title or _fallback_title(p.get("premise", "")),
        "depth": p.get("depth", "kubrick"),
        "generated_at": p.get("updated_at") or time.time(),
        "elapsed_seconds": round((p.get("updated_at") or 0) - (p.get("created_at") or 0), 1),
        "stop_reason": a.stop or p.get("stop_reason", ""),
        "confidence": p.get("confidence", 0.0),
        "coverage": p.get("coverage", 0.0),
        "source_diversity": p.get("source_diversity", 0.0),
        "provenance_quality": p.get("provenance_quality", 0.0),
        "unresolved_contradictions": open_contra,
        "overview": p.get("overview", ""),
        "boxes": boxes,
        "evidence": kept,
        "runs": runs,
        "verdicts": verdicts,
        "prior_art": prior_art,
        "reel": reel,
        "modality_counts": mods,
        "emergent_boxes": [b["name"] for b in boxes if b.get("emergent")],
    }

    out = ROOT / "web" / "public" / f"demo-{a.slug}.json"
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    print(f"evidence {len(kept)}  modality {mods}")
    print(f"verdicts {len(verdicts)} ({open_contra} contradictions)")
    print(f"readiness {snapshot['confidence']:.0%}  coverage {snapshot['coverage']:.0%}")

    pdf_path = ROOT / "web" / "public" / f"demo-{a.slug}-dossier.pdf"
    try:
        import report as report_mod

        project = {
            "id": "demo", "premise": snapshot["premise"], "title": snapshot["title"],
            "confidence": snapshot["confidence"], "coverage": snapshot["coverage"],
            "overview": snapshot["overview"], "depth": snapshot["depth"],
        }
        pdf = report_mod.build_report_pdf(
            project=project, boxes=boxes, evidence=kept, verdicts=verdicts,
            runs=runs, reel=reel, prior_art=prior_art,
        )
        pdf_path.write_bytes(pdf)
        print(f"wrote {pdf_path.name} ({len(pdf) // 1024} KB)")
    except Exception as exc:  # noqa: BLE001
        print(f"PDF build skipped: {exc}")


if __name__ == "__main__":
    main()
