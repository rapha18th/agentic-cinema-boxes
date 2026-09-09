"""Two-stage contradiction detection.

Stage 1: embedding similarity finds pairs of evidence that talk about the same
thing. Similarity alone never proves disagreement, so this only produces
candidates. It bands the score: near-duplicates and unrelated pairs are skipped.

Stage 2: Gemini reads both fragments and classifies the relationship as
supports / contradicts / contextualises / unrelated, with an explanation and the
two citations.
"""

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

import numpy as np

from . import llm
from .evidence import Evidence

RELATIONS = ("supports", "contradicts", "contextualises", "unrelated")

# For entity-anchored pairing: proper-noun tokens and years. Disagreeing
# accounts of one event often share almost no ordinary vocabulary (so the
# embedding pulls them apart) but do share the names and dates the event is
# indexed by.
_TOKEN = re.compile(r"\b(?:[A-Z][A-Za-z'’-]{2,}|1[89]\d{2}|20\d{2})\b")
_ENTITY_STOP = {
    "The", "This", "That", "These", "Those", "There", "Their", "They", "Then",
    "When", "Where", "Which", "While", "With", "From", "Into", "After", "Before",
    "During", "Between", "About", "Also", "However", "According", "Source", "Text",
    "Wikipedia", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    # Title and citation boilerplate: matched by the capitalised-word pattern but
    # says nothing about which event a fragment is about.
    "Country", "Reports", "Report", "Practices", "Human", "Rights", "Department",
    "State", "Interview", "Biography", "Facts", "Timeline", "Encyclopedia",
    "University", "Press", "Archive", "Archives", "Documents", "Document",
    "Office", "Historian", "History", "Overview", "Introduction", "Chapter",
    "Volume", "Journal", "Review", "Study", "Analysis", "Profile", "Guide",
    "News", "Article", "Page", "Home", "Search", "Results", "Collection",
    "Free", "Simple", "English", "PDF",
}


def _salient(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text or "") if t not in _ENTITY_STOP}


# A hard "contradicts" between two hobby or marketing sites is a curiosity, not
# a research finding. Keep it only when at least one side has some standing.
_CREDIBLE = (
    ".gov", ".edu", ".ac.uk", ".ac.za", "wikipedia.org", "britannica.com",
    "archive.org", "jstor.org", "cambridge.org", "oup.com", "tandfonline.com",
    "sagepub.com", "springer.com", "muse.jhu.edu", "iupress.org", "dukeupress.edu",
    "foreignaffairs.com", "bbc.", "reuters.com", "apnews.com", "nytimes.com",
    "theguardian.com", "washingtonpost.com", "aljazeera.com", "africabib.org",
    "sahistory.org.za", "hansard", "loc.gov", "history.state.gov",
)


def _credible(domain: str) -> bool:
    d = (domain or "").lower()
    return any(tok in d for tok in _CREDIBLE)


@dataclass
class Verdict:
    a_id: str
    b_id: str
    relation: str
    explanation: str
    a_cite: str
    b_cite: str
    similarity: float

    def to_dict(self) -> dict:
        return asdict(self)


def candidate_pairs(
    vectors: np.ndarray,
    evidence: list[Evidence] | None = None,
    *,
    low: float = 0.52,
    high: float = 0.92,
    max_pairs: int = 40,
) -> list[tuple[int, int, float]]:
    """Index pairs whose cosine similarity sits in the band: related enough to be
    about the same subject, not so close they are the same passage.

    Ranking matters. Sorting by raw similarity puts near-paraphrases first, and
    those almost always just agree. A real disagreement is two independent
    sources on the same event that reach different conclusions, which sits in
    the middle of the band. So rank by: independent domain, then closeness to
    the middle of the band, then similarity as a tie-break.
    """
    if vectors is None or len(vectors) < 2:
        return []
    v = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
    sims = v @ v.T
    iu = np.triu_indices(len(v), k=1)
    raw = [
        (int(i), int(j), float(sims[i, j]))
        for i, j in zip(*iu)
        if low <= sims[i, j] <= high
    ]
    doms = [getattr(e, "source_domain", "") for e in evidence] if evidence else None

    def rank(p: tuple[int, int, float]) -> float:
        i, j, s = p
        cross = 0.0
        if doms is not None:
            cross = 0.18 if (doms[i] and doms[j] and doms[i] != doms[j]) else -0.05
        mid = max(0.0, 1.0 - abs(s - 0.72) / 0.22)  # peaks where accounts diverge
        return cross + 0.55 * mid + 0.20 * s

    raw.sort(key=rank, reverse=True)
    return raw[:max_pairs]


_VERIFY_PROMPT = """Two pieces of research evidence gathered for the same film.

A ({a_cite}):
{a_text}

B ({b_cite}):
{b_text}

Classify the relationship of B to A as exactly one of:
supports, contradicts, contextualises, unrelated.

"contradicts": they make claims that cannot both be true. This includes
assigning the same event to different causes or actors, giving a different
date, number, name, or sequence for the same thing, or one asserting what the
other denies. A settled official account and a later first-hand admission that
name different perpetrators of the same act contradict each other.
"contextualises": they differ but are reconcilable, covering a different time,
place, or scope of the same subject.
"supports": they agree or one simply adds detail to the other.
"unrelated": they are not about the same specific fact.

Judge the substance. Two sources can contradict even when their wording,
framing, and vocabulary are entirely different.

Write the explanation in plain, declarative sentences. State what A says, then
state what B says. Do not use "whereas", "while", "unlike", "not X but Y", or
any other contrastive construction. Do not use an em dash.

Return JSON: {{"relation": "...", "explanation": "one or two sentences"}}"""


def verify(a: Evidence, b: Evidence, similarity: float) -> Verdict:
    raw = llm.generate_json(
        _VERIFY_PROMPT.format(
            a_cite=a.cite(), a_text=a.text[:1200], b_cite=b.cite(), b_text=b.text[:1200]
        )
    )
    rel = str(raw.get("relation", "unrelated")).strip().lower()
    if rel not in RELATIONS:
        rel = "unrelated"
    return Verdict(
        a_id=a.id,
        b_id=b.id,
        relation=rel,
        explanation=str(raw.get("explanation", "")).strip(),
        a_cite=a.cite(),
        b_cite=b.cite(),
        similarity=round(similarity, 3),
    )


def entity_pairs(
    evidence: list[Evidence], *, min_docs: int = 2, max_docs: int = 16,
    min_shared: int = 3, min_distinct: int = 2, distinct_df: int = 6, cap: int = 200,
) -> dict[tuple[int, int], int]:
    """Pairs of fragments that share several proper nouns or dates. Two accounts
    that attribute the same event to different actors share the names and dates
    that pin the event, so this reaches contradictions the embedding band
    misses. A pair also needs a couple of *distinctive* shared names, or every
    fragment about Zambia pairs with every other. Returns {(i, j): score}."""
    if not evidence:
        return {}
    tok_docs: dict[str, list[int]] = defaultdict(list)
    for idx, e in enumerate(evidence):
        for t in _salient(e.text):
            tok_docs[t].append(idx)
    total: dict[tuple[int, int], int] = defaultdict(int)
    distinct: dict[tuple[int, int], int] = defaultdict(int)
    for t, idxs in tok_docs.items():
        df = len(idxs)
        if not (min_docs <= df <= max_docs):
            continue
        rare = df <= distinct_df
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                p = (idxs[a], idxs[b])
                total[p] += 1
                if rare:
                    distinct[p] += 1
    out = {
        p: n for p, n in total.items()
        if n >= min_shared and distinct.get(p, 0) >= min_distinct
    }
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:cap])


def find_contradictions(
    evidence: list[Evidence],
    vectors: np.ndarray,
    *,
    max_checks: int = 24,
    max_workers: int = 4,
    focus_ids: set[str] | None = None,
) -> list[Verdict]:
    """Two candidate sources feed the verifier: the embedding band (same
    subject, mid similarity) and entity anchoring (fragments that share several
    names or dates). The union is ranked so independent sources on the same
    event come first. Each pair's Gemini verdict is independent, so they verify
    concurrently. `focus_ids` keeps only pairs with at least one endpoint in
    that set, so a targeted pass stays on its question."""
    if not evidence or vectors is None or len(vectors) < 2:
        return []
    v = np.asarray(vectors, dtype=np.float32)
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    focus = {i for i, e in enumerate(evidence) if e.id in focus_ids} if focus_ids else None

    ent = entity_pairs(evidence, cap=max_checks * 4)
    band = {(i, j): s for i, j, s in candidate_pairs(vectors, evidence, max_pairs=max_checks * 4)}

    doms = [getattr(e, "source_domain", "") for e in evidence]
    titles = [{w for w in re.findall(r"[a-z]+", (getattr(e, "title", "") or "").lower())
               if len(w) > 2}
              for e in evidence]

    def same_series(i: int, j: int) -> bool:
        a, b = titles[i], titles[j]
        if len(a) < 4 or len(b) < 4:
            return False
        return len(a & b) / len(a | b) >= 0.7  # one publication, different year

    scored: list[tuple[float, int, int, float]] = []
    for (i, j) in set(band) | set(ent):
        if focus is not None and i not in focus and j not in focus:
            continue
        if evidence[i].url and evidence[i].url == evidence[j].url:
            continue  # same page: a disagreement there is a scraping artefact
        if same_series(i, j):
            continue  # an annual report across two years is not a contradiction
        sim = float(v[i] @ v[j])
        cross = 0.18 if (doms[i] and doms[j] and doms[i] != doms[j]) else -0.05
        mid = max(0.0, 1.0 - abs(sim - 0.72) / 0.22)
        rank = cross + 0.5 * mid + 0.18 * sim + 0.12 * min(ent.get((i, j), 0), 6)
        scored.append((rank, i, j, sim))
    scored.sort(reverse=True)
    picks = scored[:max_checks]
    if not picks:
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(picks))) as ex:
        results = list(ex.map(
            lambda p: verify(evidence[p[1]], evidence[p[2]], p[3]), picks
        ))
    by_id = {e.id: e for e in evidence}

    def has_standing(r: Verdict) -> bool:
        a, b = by_id.get(r.a_id), by_id.get(r.b_id)
        return _credible(getattr(a, "source_domain", "")) or _credible(getattr(b, "source_domain", ""))

    kept = [r for r in results if r.relation in ("contradicts", "contextualises")]
    # A real contradiction is the finding. Drop the ones where neither side has
    # any standing, and keep only a few "contextualises" notes, contradictions
    # first.
    contra = [r for r in kept if r.relation == "contradicts" and has_standing(r)]
    context = sorted((r for r in kept if r.relation == "contextualises" and has_standing(r)),
                     key=lambda r: -r.similarity)[:4]
    return sorted(contra, key=lambda r: -r.similarity) + context
