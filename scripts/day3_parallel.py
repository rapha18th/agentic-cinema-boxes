"""Day 3 proof: the Parallel Search API key works and returns inspectable results.

Run: python scripts/day3_parallel.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from boxes import parallel_search as ps  # noqa: E402


def main() -> None:
    print("key present:", ps.has_key())
    hits = ps.search(
        "Vienna banking hall interiors in the 1920s",
        objective="Reference material on how Vienna bank interiors looked around 1929, for production design.",
        mode="fast",
        max_results=5,
    )
    print(f"hits: {len(hits)}\n")
    for h in hits:
        print(f"- {h.title}")
        print(f"  {h.url}  ({h.publish_date})")
        print(f"  {h.text[:220].replace(chr(10), ' ')}...\n")


if __name__ == "__main__":
    main()
