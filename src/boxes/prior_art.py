"""Prior-art survey: where this premise sits against films that already exist.

TMDB supplies the candidate pool and metadata (not IMDb, which has no official
API). Parallel Search adds one broadening pass past TMDB's keyword tagging, so
festival and foreign titles TMDB under-tags aren't missed. Gemini Embedding 2
ranks candidates by meaning, not genre tags, so "a heist without entering the
vault" surfaces its real neighbours regardless of tone. Gemini then reads the
survivors and states which angles are unclaimed, always naming which films
that claim was checked against. Never claims absolute originality, only
originality relative to the surveyed set.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import httpx

from . import config, llm
from .embeddings import TASK_SEARCH, cosine, embed_texts
from .parallel_search import search as parallel_search

_POSTER = "https://image.tmdb.org/t/p/w342"


@dataclass
class Neighbor:
    title: str
    year: str = ""
    source: str = "tmdb"  # tmdb | web
    url: str = ""
    poster_url: str = ""
    overview: str = ""
    similarity: float = 0.0
    engine: str = ""
    pov: str = ""
    tone: str = ""
    moral_arc: str = ""
    ending: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UnclaimedAngle:
    angle: str
    why: str
    contrast_titles: list[str] = field(default_factory=list)
    prompt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriorArtReport:
    premise: str
    keywords: list[str]
    surveyed: int
    neighbors: list[Neighbor]
    unclaimed_angles: list[UnclaimedAngle]
    generated_at: float

    def to_dict(self) -> dict:
        return {
            "premise": self.premise,
            "keywords": self.keywords,
            "surveyed": self.surveyed,
            "neighbors": [n.to_dict() for n in self.neighbors],
            "unclaimed_angles": [a.to_dict() for a in self.unclaimed_angles],
            "generated_at": self.generated_at,
        }


def _tmdb_get(path: str, key: str, **params) -> dict:
    r = httpx.get(f"{config.TMDB_URL}{path}", params={"api_key": key, **params}, timeout=15.0)
    r.raise_for_status()
    return r.json()


_SEED_PROMPT = """A film premise:

{premise}

Return JSON: {{"logline": one sentence, "tmdb_query": a short movie-title-style
search string (3 to 6 words) capturing the closest existing film concept,
"keywords": 3 to 6 short genre/theme words for a movie keyword search (for
example "heist", "bank fraud", "vienna", "1929", "whistleblower")}}."""


def _seed(premise: str) -> dict:
    raw = llm.generate_json(_SEED_PROMPT.format(premise=premise))
    return raw if isinstance(raw, dict) else {}


def _tmdb_candidates(seed: dict, key: str) -> list[Neighbor]:
    found: dict[int, Neighbor] = {}

    def add(items: list[dict]) -> None:
        for it in items:
            tid = it.get("id")
            if not tid or tid in found or not it.get("title"):
                continue
            found[tid] = Neighbor(
                title=it["title"],
                year=(it.get("release_date") or "")[:4],
                source="tmdb",
                url=f"https://www.themoviedb.org/movie/{tid}",
                poster_url=_POSTER + it["poster_path"] if it.get("poster_path") else "",
                overview=it.get("overview", ""),
            )

    def by_query(q: str) -> None:
        if not q:
            return
        try:
            add(_tmdb_get("/search/movie", key, query=q).get("results", [])[:10])
        except httpx.HTTPError:
            pass

    def by_keyword(kw: str) -> None:
        try:
            hits = _tmdb_get("/search/keyword", key, query=kw).get("results", [])
            if not hits:
                return
            add(_tmdb_get("/discover/movie", key, with_keywords=hits[0]["id"],
                          sort_by="popularity.desc").get("results", [])[:10])
        except httpx.HTTPError:
            pass

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(by_query, [seed.get("tmdb_query", "")]))
        list(ex.map(by_keyword, (seed.get("keywords") or [])[:5]))

    seed_ids = list(found.keys())[:3]

    def by_similar(tid: int) -> None:
        try:
            add(_tmdb_get(f"/movie/{tid}/similar", key).get("results", [])[:8])
        except httpx.HTTPError:
            pass

    if seed_ids:
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(by_similar, seed_ids))

    return list(found.values())


def _web_candidates(premise: str) -> list[Neighbor]:
    try:
        hits = parallel_search(
            f"films with a premise similar to: {premise}", mode="fast", max_results=8
        )
    except Exception:  # noqa: BLE001
        return []
    return [
        Neighbor(title=h.title or h.url, source="web", url=h.url, overview=h.text[:400])
        for h in hits if h.url
    ]


_SCHEMA_PROMPT = """A film in development:

PREMISE: {premise}

Existing films ranked closest to this premise by meaning, not genre:
{catalog}

For EACH film return its comparison fields. Then, looking across all of them,
state where THIS premise is NOT yet occupied: which combinations of engine,
POV, tone, or ending none of these films use. Every claim about what "hasn't
been done" must name which of the listed films it was checked against, and
must not claim absolute originality, only originality relative to this list.

Write "why" in plain, spare, declarative sentences. State each film's stance
on its own, plainly. Never write a contrastive sentence joining two films
with "while", "whereas", or "unlike".

Return JSON: {{"films": [{{"title", "engine" (what is exploited and whether
it is a flaw or a shipped feature, one phrase), "pov" (perpetrator, bystander,
investigator, or victim), "tone" (one word, farce to tragedy), "moral_arc"
(one phrase), "ending" (one phrase)}}], "unclaimed_angles": [{{"angle" (one
sentence), "why" (one sentence), "contrast_titles" (list of titles from
above), "prompt" (one sentence nudging the premise toward this angle)}}]}}
(3 to 6 unclaimed_angles)."""


def survey(premise: str, *, n: int = 12) -> PriorArtReport:
    """Seed candidates from TMDB (+ one Parallel pass), rank by embedding
    similarity to the premise, then have Gemini compare structure and name
    what's unclaimed. Degrades to a Parallel-only pool if TMDB has no key."""
    key = config.tmdb_api_key()
    seed = _seed(premise)
    keywords = seed.get("keywords") or []

    pool: list[Neighbor] = []
    if key:
        pool += _tmdb_candidates(seed, key)
    pool += _web_candidates(premise)
    if not pool:
        return PriorArtReport(premise=premise, keywords=keywords, surveyed=0,
                              neighbors=[], unclaimed_angles=[], generated_at=time.time())

    pool = pool[:40]
    texts = [f"{c.title} ({c.year}). {c.overview}".strip() for c in pool]
    vecs = embed_texts(texts, dim=768)
    qv = embed_texts([premise], dim=768, prefix=TASK_SEARCH)[0]
    for c, v in zip(pool, vecs):
        c.similarity = round(cosine(qv, v), 3)
    pool.sort(key=lambda c: -c.similarity)
    top = pool[:n]

    catalog = "\n".join(f"- {c.title} ({c.year}): {c.overview[:200]}" for c in top)
    raw = llm.generate_json(_SCHEMA_PROMPT.format(premise=premise, catalog=catalog))
    raw = raw if isinstance(raw, dict) else {}
    by_title = {c.title: c for c in top}
    for f in raw.get("films", []):
        c = by_title.get(f.get("title", ""))
        if not c:
            continue
        c.engine = f.get("engine", "")
        c.pov = f.get("pov", "")
        c.tone = f.get("tone", "")
        c.moral_arc = f.get("moral_arc", "")
        c.ending = f.get("ending", "")

    angles = [
        UnclaimedAngle(
            angle=a.get("angle", ""), why=a.get("why", ""),
            contrast_titles=a.get("contrast_titles", []) or [],
            prompt=a.get("prompt", ""),
        )
        for a in raw.get("unclaimed_angles", [])
    ]

    return PriorArtReport(
        premise=premise, keywords=keywords, surveyed=len(pool),
        neighbors=top, unclaimed_angles=angles, generated_at=time.time(),
    )
