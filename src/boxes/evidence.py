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
    source_tier: str = ""  # primary | documentary | web | director
    quality_score: float = 0.0  # transparent, deterministic provenance score
    image_url: str = ""  # for modality == image: the picture itself
    media_url: str = ""  # for image/pdf/audio/video: the full asset URL
    media_mime: str = ""  # the asset's MIME type
    media_trimmed: bool = False  # audio/video was clipped for embedding; full at media_url
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
        if not self.source_tier:
            self.source_tier = _source_tier(self.source_domain, self.url)
        if not self.quality_score:
            self.quality_score = _quality_score(self)

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


_PRIMARY_HOSTS = (
    ".gov", ".edu", "archives.", "archive.org", "loc.gov", "nasa.gov",
    "si.edu", "europeana.eu", "parliament.", "congress.gov", "govinfo.gov",
)
_DOCUMENTARY_HOSTS = (
    "britannica.com", "history.com", "bbc.", "reuters.com", "apnews.com",
    "nytimes.com", "theguardian.com", "smithsonianmag.com",
)


def _source_tier(domain: str, url: str) -> str:
    host = (domain or urlparse(url).netloc).lower()
    if host == "director":
        return "director"
    if any(token in host for token in _PRIMARY_HOSTS):
        return "primary"
    if any(token in host for token in _DOCUMENTARY_HOSTS):
        return "documentary"
    return "web"


def _quality_score(e: "Evidence") -> float:
    """A visible provenance signal, not a truth probability.

    The score rewards inspectability and source class. It deliberately avoids
    asking a model to grade its own evidence.
    """
    tier = {"primary": 0.48, "director": 0.45, "documentary": 0.36, "web": 0.24}.get(e.source_tier, 0.2)
    score = tier
    score += 0.18 if e.url.startswith("https://") else 0.08 if e.url else 0.0
    score += 0.12 if e.title else 0.0
    score += 0.12 if e.publish_date else 0.0
    score += 0.10 if len(e.text.strip()) >= 180 else 0.04 if e.text.strip() else 0.0
    return round(min(1.0, score), 3)
