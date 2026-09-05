"""Post-process a demo snapshot: drop polluting sources and flag any house-style
slips in the generated prose so the read-only /demo page stays clean.

    python scripts/clean_snapshot.py web/src/demo/snapshot.json \
        --title "ELIZA · 1966" --stop "every objective is well covered"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_JUNK = (
    "instagram.com", "shiksha.com", "careers360.com", "collegedunia.com",
    "quora.com", "pinterest.", "facebook.com", "tiktok.com",
)
_CREDIBLE = (
    ".gov", ".edu", ".ac.uk", "wikipedia.org", "archive.org", "loc.gov",
    "si.edu", "computerhistory.org", "multicians.org", "ieee.org", "jstor.org",
    "nature.com", "acm.org", "bitsavers.org", "britannica.com", "nasa.gov",
    "smithsonianmag.com", "hathitrust.org", "mit.edu",
)
_ANTITHESIS = re.compile(
    r"\b(whereas|rather than|instead of|unlike|not only|avoiding)\b|—|,\s+not\s+\w", re.I,
)


def _has(domain: str, toks: tuple[str, ...]) -> bool:
    d = (domain or "").lower()
    return any(t in d for t in toks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--title", default="")
    ap.add_argument("--stop", default="")
    a = ap.parse_args()

    p = Path(a.path)
    d = json.loads(p.read_text(encoding="utf-8"))

    dom = {e["id"]: e.get("source_domain", "") for e in d["evidence"]}
    drop = {e["id"] for e in d["evidence"] if _has(e.get("source_domain", ""), _JUNK)}
    seen: set[str] = set()
    kept_ev = []
    for e in d["evidence"]:
        if e["id"] in drop or e["id"] in seen:
            continue
        seen.add(e["id"])
        kept_ev.append(e)
    removed = len(d["evidence"]) - len(kept_ev)
    d["evidence"] = kept_ev
    keep = {e["id"] for e in d["evidence"]}

    d["verdicts"] = [
        v for v in d["verdicts"]
        if v.get("a_id") in keep and v.get("b_id") in keep
        and (_has(dom.get(v.get("a_id"), ""), _CREDIBLE) or _has(dom.get(v.get("b_id"), ""), _CREDIBLE))
    ]
    d["unresolved_contradictions"] = sum(1 for v in d["verdicts"] if v["relation"] == "contradicts")

    for b in d["boxes"]:
        mine = [e for e in d["evidence"] if e.get("objective_id") == b["id"]]
        b["evidence_count"] = len(mine)
        b["distinct_domains"] = len({e.get("source_domain") for e in mine if e.get("source_domain")})

    mods: dict[str, int] = {}
    for e in d["evidence"]:
        mods[e.get("modality", "text")] = mods.get(e.get("modality", "text"), 0) + 1
    d["modality_counts"] = mods

    if a.title:
        d["title"] = a.title
    if a.stop:
        d["stop_reason"] = a.stop
    d.setdefault("stop_reason", "")

    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    slips = []
    fields = [("overview", d.get("overview", ""))]
    fields += [(f"box[{b['name']}].summary", b.get("summary", "")) for b in d["boxes"]]
    fields += [(f"box[{b['name']}].{k}", b.get(k, "")) for b in d["boxes"] for k in ("description", "rationale")]
    fields += [(f"reel[{i}].note", x.get("note", "")) for i, x in enumerate(d.get("reel", []))]
    fields += [(f"angle[{i}].why", x.get("why", "")) for i, x in enumerate(d.get("prior_art", {}).get("unclaimed_angles", []))]
    fields += [(f"verdict[{i}].explanation", v.get("explanation", "")) for i, v in enumerate(d["verdicts"])]
    for name, text in fields:
        if _ANTITHESIS.search(text or ""):
            slips.append(f"  {name}: {text.strip()[:200]}")

    print(f"removed {removed} fragments (junk + duplicate id); {len(d['evidence'])} kept; "
          f"{len(d['verdicts'])} verdicts ({d['unresolved_contradictions']} contradictions)")
    print(f"modality {mods}")
    if slips:
        print(f"\nHOUSE-STYLE SLIPS ({len(slips)}) — hand-edit these strings in {p.name}:")
        print("\n".join(slips))
    else:
        print("no house-style slips found")


if __name__ == "__main__":
    sys.exit(main())
