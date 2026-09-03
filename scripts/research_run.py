"""Run THE BOXES end to end and show the ledger, coverage, confidence,
contradictions, and a reference reel.

    python scripts/research_run.py                 # scout depth, default premise
    python scripts/research_run.py production "A premise ..."
"""

from __future__ import annotations

import builtins
import functools
import sys

sys.path.insert(0, "src")
print = functools.partial(builtins.print, flush=True)  # stream under a pipe

from boxes import research_loop as rl  # noqa: E402
from boxes import reel  # noqa: E402
from boxes import parallel_search as ps  # noqa: E402

DEFAULT_PREMISE = (
    "Vienna, 1929. During economic turmoil, four bank employees discover a flaw "
    "that could let them remove millions without opening the vault."
)


def on_event(ev: dict) -> None:
    t = ev.get("type")
    if t == "plan":
        print("\nRESEARCH PLAN")
        for o in ev["objectives"]:
            print(f"  {o['name']:<26} {o['description']}")
    elif t == "search":
        print(f"\n  search  {ev['objective']}")
        for q in ev["queries"]:
            print(f"          q: {q}")
    elif t == "extract":
        extra = ", ".join(f"{ev[k]} {k}" for k in ("images", "docs", "av") if ev.get(k))
        print(f"  extract {ev['objective']}: {ev['sources']} sources" + (f" + {extra}" if extra else ""))
    elif t == "coverage":
        print(f"  -> {ev['summary']}")
    elif t == "emergent_gap":
        o = ev["objective"]
        print(f"\n  EMERGENT GAP: opening box {o['name']} — {o['description']}")
    elif t == "contradiction":
        v = ev["verdict"]
        print(f"  ! contradiction: {v['a_cite']}  vs  {v['b_cite']}")
    elif t == "stop":
        print(f"\nSTOP: {ev['reason']}")


def main() -> None:
    args = sys.argv[1:]
    depth = args[0] if args and args[0] in ("scout", "production", "kubrick") else "scout"
    premise = args[1] if len(args) > 1 else (args[0] if args and depth == "scout" and args[0] not in ("scout",) else DEFAULT_PREMISE)
    if premise in ("scout", "production", "kubrick"):
        premise = DEFAULT_PREMISE

    print(f"depth={depth}  parallel_key={ps.has_key()}")
    print(f"premise: {premise}")

    proj = rl.run(premise, depth=depth, on_event=on_event)

    print("\n" + "=" * 64)
    print("RESEARCH LEDGER")
    print("=" * 64)
    print(proj.ledger.render())

    rep = proj.reports[-1]
    print("\nCOVERAGE BY BOX")
    for c in sorted(rep.per_objective, key=lambda c: c.score):
        bar = "#" * int(round(c.score * 20))
        print(f"  {c.name:<26} {c.score:4.2f} {bar:<20}  {c.evidence_count} items / {c.distinct_domains} domains")
    print(f"\n  {rep.summary()}")

    if proj.contradictions:
        print("\nVERIFIED VERDICTS")
        for v in proj.contradictions:
            print(f"  [{v.relation}] {v.explanation}")
            print(f"      A: {v.a_cite}")
            print(f"      B: {v.b_cite}")

    from collections import Counter
    mods = Counter(e.modality for e in proj.evidence)
    print(f"\nMULTIMODAL SPACE: " + " · ".join(f"{v} {k}" for k, v in mods.most_common()))

    print("\nREFERENCE REEL")
    for b in reel.build_reel(premise, proj.evidence):
        print(f"  {b.t}  {b.title} — {b.note}")
        for s in b.sources[:3]:
            tag = "" if s["modality"] == "text" else f"{s['modality'].upper()} "
            print(f"         {tag}{s['cite']}  {s['url'] or s.get('media_url') or s.get('image_url')}")


if __name__ == "__main__":
    main()
