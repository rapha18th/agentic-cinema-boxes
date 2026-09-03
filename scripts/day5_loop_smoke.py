"""Day 5 smoke test: the research loop runs end to end on one small topic.

With no PARALLEL_API_KEY set, the Parallel client returns a labelled stub, so the
loop wiring is exercised without live search. Set the key for a real run.

Run: python scripts/day5_loop_smoke.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from boxes import parallel_search as ps  # noqa: E402
from boxes.research_loop import run  # noqa: E402

PREMISE = "A heist film set in 1929 Vienna during the hyperinflation."


def main() -> None:
    print(f"parallel key present: {ps.has_key()}")
    state = run(PREMISE, max_rounds=2, min_growth=3)
    print("\n--- loop log ---")
    for line in state.log:
        print(line)
    print(f"\nfinal index size: {len(state.store)}")


if __name__ == "__main__":
    main()
