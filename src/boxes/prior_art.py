"""Prior-art survey: where this premise sits against films that already exist.

TMDB supplies the candidate pool and metadata through its free developer API.
IMDb licenses its data as an enterprise product on AWS Data Exchange. The pool
is seeded four ways: a concept title search, the specific films the model
names as thematic comparables, an OR-discover pass over resolved theme
keywords ranked by popularity and by vote count, and TMDB's own similar-title
graph for the concept matches. Gemini Embedding 2 then ranks the pool by
meaning against two queries, the premise as written and the concept it is
about, and each candidate keeps its better match. Gemini reads the survivors
and states which angles are unclaimed, always naming which films that claim
was checked against. Never claims absolute originality, only originality
relative to the surveyed set.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import httpx

from . import config, llm
from .embeddings import TASK_SEARCH, cosine, embed_texts

_POSTER = "https://image.tmdb.org/t/p/w342"


@dataclass
class Neighbor:
    title: str
    year: str = ""
    source: str = "tmdb"  # tmdb | web
    origin: str = "keyword"  # named | concept | similar | keyword
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

Return JSON with these keys:
- "logline": one sentence naming the core dramatic idea, not the setting.
- "tmdb_query": a short movie-title-style search string, 3 to 6 words, for the
  closest existing film concept.
- "keywords": 3 to 6 short theme words for a movie keyword search, such as
  "artificial intelligence", "loneliness", "surveillance", "1960s".
- "comparable_films": 3 to 6 titles of real existing films this premise most
  resembles in theme or dramatic situation."""


def _seed(premise: str) -> dict:
    raw = llm.generate_json(_SEED_PROMPT.format(premise=premise))
    return raw if isinstance(raw, dict) else {}


def _tmdb_candidates(seed: dict, key: str) -> list[Neighbor]:
    found: dict[int, Neighbor] = {}

    def add(items: list[dict], *, min_votes: int = 0, origin: str = "keyword") -> None:
        for it in items:
            tid = it.get("id")
            if not tid or tid in found or not it.get("title"):
                continue
            # A keyword-discover pass drags in barely-released films with a thin
            # overview that then embeds noisily. Trust the concept query and the
            # named comparables unconditionally; gate the broad passes on votes.
            if min_votes and (it.get("vote_count") or 0) < min_votes:
                continue
            found[tid] = Neighbor(
                title=it["title"],
                year=(it.get("release_date") or "")[:4],
                source="tmdb",
                origin=origin,
                url=f"https://www.themoviedb.org/movie/{tid}",
                poster_url=_POSTER + it["poster_path"] if it.get("poster_path") else "",
                overview=it.get("overview", ""),
            )

    def search_movie(q: str, limit: int = 6, *, by_votes: bool = False,
                     origin: str = "concept") -> None:
        if not q:
            return
        try:
            results = _tmdb_get("/search/movie", key, query=q).get("results", [])
            if by_votes:
                results.sort(key=lambda r: -(r.get("vote_count") or 0))
            add(results[:limit], origin=origin)
        except httpx.HTTPError:
            pass

    # 1. the concept query, plus every film the model says the premise resembles.
    #    Named comparables are the recall fix: embedding ranking can only reorder
    #    the pool, so "Her" has to be put in it before it can rank.
    search_movie(seed.get("tmdb_query", ""), limit=10, origin="concept")
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda t: search_movie(t, 2, by_votes=True, origin="named"),
                    (seed.get("comparable_films") or [])[:6]))
    core_ids = list(found.keys())[:5]

    # 2. resolve theme words to TMDB keyword ids, then one OR-discover pass over
    #    all of them, by popularity and again by vote count so a well-known older
    #    film is not buried under this year's releases.
    kw_ids: list[str] = []
    for kw in (seed.get("keywords") or [])[:6]:
        try:
            hits = _tmdb_get("/search/keyword", key, query=kw).get("results", [])
            kw_ids += [str(h["id"]) for h in hits[:2]]
        except httpx.HTTPError:
            pass
    if kw_ids:
        joined = "|".join(dict.fromkeys(kw_ids))
        for sort in ("popularity.desc", "vote_count.desc"):
            try:
                add(_tmdb_get("/discover/movie", key, with_keywords=joined,
                              sort_by=sort).get("results", [])[:25], min_votes=30)
            except httpx.HTTPError:
                pass

    # 3. TMDB's own "similar" for the concrete concept matches.
    def by_similar(tid: int) -> None:
        try:
            add(_tmdb_get(f"/movie/{tid}/similar", key).get("results", [])[:8],
                min_votes=15, origin="similar")
        except httpx.HTTPError:
            pass

    if core_ids:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(by_similar, core_ids))

    return list(found.values())


_SCHEMA_PROMPT = """A film in development:

PREMISE: {premise}

Existing films ranked closest to this premise by meaning, not genre:
{catalog}

For EACH film return its comparison fields. Then, looking across all of them,
state where THIS premise is NOT yet occupied: which combinations of engine,
POV, tone, or ending none of these films use. Every claim about what "hasn't
been done" must name which of the listed films it was checked against, and
must not claim absolute originality, only originality relative to this list.

Write every string you return ("angle", "why", "prompt", every phrase) in
plain, spare, declarative sentences. State each film's stance on its own,
plainly. Never use an em dash. Never use a contrastive construction:
no "while", "whereas", "unlike", "rather than", "instead of", "as opposed
to", "not X but Y", "X, not Y".

Return JSON: {{"films": [{{"title", "engine" (what is exploited and whether
it is a flaw or a shipped feature, one phrase), "pov" (perpetrator, bystander,
investigator, or victim), "tone" (one word, farce to tragedy), "moral_arc"
(one phrase), "ending" (one phrase)}}], "unclaimed_angles": [{{"angle" (one
sentence), "why" (one sentence), "contrast_titles" (list of titles from
above), "prompt" (one sentence nudging the premise toward this angle)}}]}}
(3 to 6 unclaimed_angles)."""


def survey(premise: str, *, n: int = 12) -> PriorArtReport:
    """Seed candidates from TMDB, rank by embedding similarity, then have Gemini
    compare structure and name what's unclaimed. Returns an empty report if
    TMDB has no key."""
    key = config.tmdb_api_key()
    seed = _seed(premise)
    keywords = seed.get("keywords") or []

    pool: list[Neighbor] = _tmdb_candidates(seed, key) if key else []
    if not pool:
        return PriorArtReport(premise=premise, keywords=keywords, surveyed=0,
                              neighbors=[], unclaimed_angles=[], generated_at=time.time())

    pool = pool[:80]
    texts = [f"{c.title} ({c.year}). {c.overview}".strip() for c in pool]
    vecs = embed_texts(texts, dim=768)
    # Rank against two queries: the premise as written, and the concept the
    # premise is about. A period premise foregrounds place and year, so a
    # theme-mate like "Her" scores low against the literal text and high
    # against the concept. Candidates the model named as comparable get a small
    # bonus: that is its explicit judgement, the signal to trust most.
    logline = (seed.get("logline") or "").strip()
    concept = f"{logline} Themes: {', '.join(keywords)}".strip(" .") or premise
    q_prem, q_concept = embed_texts([premise, concept], dim=768, prefix=TASK_SEARCH)
    bonus = {"named": 0.05, "concept": 0.03}
    for c, v in zip(pool, vecs):
        sim = 0.25 * cosine(q_prem, v) + 0.75 * cosine(q_concept, v)
        c.similarity = round(sim + bonus.get(c.origin, 0.0), 3)
    pool.sort(key=lambda c: -c.similarity)

    # TMDB keeps several records for some films (a re-release, a restoration).
    # Keep the best-scoring record per title.
    seen: set[str] = set()
    deduped: list[Neighbor] = []
    for c in pool:
        k = c.title.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(c)
    pool = deduped
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
