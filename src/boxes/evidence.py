"""Evidence is the unit of research. Every fragment THE BOXES keeps carries its
full provenance, so the product can always answer "says who, from where, when".
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse


@dataclass
class Evidence:
    text: str
    url: str
    title: str = ""
    source_domain: str = ""
    publish_date: str | None = None
    modality: str = "text"  # text | image | audio | pdf | video
    objective_id: str = ""  # which research objective produced this
    query: str = ""  # the Parallel query or objective that surfaced it
    retrieved_at: float = field(default_factory=time.time)
    relevance_reason: str = ""  # why the agent kept it
    license_note: str = ""  # rights status where known
    image_url: str = ""  # for modality == image: the picture itself
    round: int = 0  # which research round produced this
    id: str = ""
    # Precomputed embedding. Set for images (embedded as picture + caption);
    # left None for text, which the loop batch-embeds. Never serialized.
    vector: list[float] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.source_domain and self.url:
            try:
                self.source_domain = urlparse(self.url).netloc.lower().removeprefix("www.")
            except Exception:
                self.source_domain = ""
        if not self.id:
            key = self.image_url or f"{self.url}|{self.text[:160]}"
            self.id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("vector", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    def cite(self) -> str:
        bits = [self.title or self.source_domain or self.url]
        if self.source_domain and self.source_domain not in bits[0]:
            bits.append(self.source_domain)
        if self.publish_date:
            bits.append(self.publish_date)
        return " · ".join(b for b in bits if b)
