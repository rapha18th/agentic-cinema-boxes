"""The research ledger. A visible, plain record of what the agent did each round,
so a judge can follow the reasoning without narration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict


@dataclass
class RoundRecord:
    run: int
    sources_examined: int = 0
    evidence_indexed: int = 0
    images_indexed: int = 0
    sources_extracted: int = 0  # sources enriched through Parallel Extract
    coverage_before: float = 0.0
    coverage_after: float = 0.0
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    new_boxes: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)  # [{objective, queries}]
    next_action: str = ""
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        lines = [
            f"RESEARCH RUN {self.run:03d}",
            f"  {self.sources_examined:>4} sources examined",
            f"  {self.evidence_indexed:>4} evidence fragments indexed",
        ]
        if self.images_indexed:
            lines.append(f"  {self.images_indexed:>4} images indexed")
        if self.sources_extracted:
            lines.append(f"  {self.sources_extracted:>4} sources enriched via Parallel Extract")
        lines.append(
            f"  coverage    {self.coverage_before:.0%} -> {self.coverage_after:.0%}"
        )
        lines.append(
            f"  confidence  {self.confidence_before:.0%} -> {self.confidence_after:.0%}"
        )
        if self.new_boxes:
            lines.append("  new boxes opened:")
            lines += [f"    + {b}" for b in self.new_boxes]
        if self.conflicts:
            lines.append("  conflicts detected:")
            lines += [f"    ! {c}" for c in self.conflicts]
        if self.next_action:
            lines.append(f"  next action:")
            lines.append(f"    -> {self.next_action}")
        return "\n".join(lines)


class Ledger:
    def __init__(self) -> None:
        self.rounds: list[RoundRecord] = []

    def add(self, rec: RoundRecord) -> None:
        self.rounds.append(rec)

    def render(self) -> str:
        return "\n\n".join(r.render() for r in self.rounds)

    def to_list(self) -> list[dict]:
        return [r.to_dict() for r in self.rounds]
