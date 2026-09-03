"""The deterministic outer loop for THE BOXES.

split topic -> search each sub-topic -> embed and index -> find coverage gaps ->
write new searches for the gaps -> repeat until coverage stops improving.

This is the "it files its own boxes" behaviour. The LLM is used only to split a
premise into sub-topics and to turn a sparse cluster back into fresh queries.
Everything else is arithmetic on vectors.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import config
from . import parallel_search as ps
from .embeddings import client as _llm
from .embeddings import embed_texts
from .vectorstore import VectorStore


@dataclass
class LoopState:
    premise: str
    store: VectorStore = field(default_factory=lambda: VectorStore(dim=768))
    rounds: int = 0
    log: list[str] = field(default_factory=list)


def split_into_subtopics(premise: str, n: int = 6) -> list[str]:
    prompt = (
        f"Break this film premise into {n} concrete research sub-topics a "
        f"production would need. Reply as a JSON list of short strings only.\n\n{premise}"
    )
    r = _llm().models.generate_content(model=config.CHAT_MODEL, contents=prompt)
    txt = (r.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return [str(x) for x in json.loads(txt)][:n]
    except Exception:
        return [line.strip("-* ") for line in txt.splitlines() if line.strip()][:n]


def queries_for_gap(premise: str, sample_texts: list[str], n: int = 4) -> list[str]:
    prompt = (
        "These snippets sit at the sparse edge of our research coverage for the "
        f"premise below. Write {n} new web search queries that would fill the gap "
        "around them. JSON list of strings only.\n\n"
        f"PREMISE: {premise}\n\nSNIPPETS:\n- " + "\n- ".join(t[:200] for t in sample_texts)
    )
    r = _llm().models.generate_content(model=config.CHAT_MODEL, contents=prompt)
    txt = (r.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return [str(x) for x in json.loads(txt)][:n]
    except Exception:
        return [line.strip("-* ") for line in txt.splitlines() if line.strip()][:n]


def _search_and_index(state: LoopState, queries: list[str], topic_label: str) -> int:
    added = 0
    for q in queries:
        hits = ps.search(q, max_results=8)
        texts = [f"{h.title}. {h.text}".strip() for h in hits if h.text or h.title]
        if not texts:
            continue
        vecs = embed_texts(texts, dim=768)
        state.store.add(vecs, [{"topic": topic_label, "query": q, "text": t[:500], "url": h.url}
                               for t, h in zip(texts, hits)])
        added += len(texts)
    return added


def run(premise: str, *, max_rounds: int = 3, min_growth: int = 4) -> LoopState:
    state = LoopState(premise=premise)
    subtopics = split_into_subtopics(premise)
    state.log.append(f"subtopics: {subtopics}")

    added = _search_and_index(state, subtopics, "seed")
    state.log.append(f"round 0: indexed {added}, size {len(state.store)}")

    while state.rounds < max_rounds:
        state.rounds += 1
        gap_idx = state.store.coverage_gaps(k=3, quantile=0.15)
        if not gap_idx:
            state.log.append(f"round {state.rounds}: no gaps found, stopping")
            break
        sample = [state.store._meta[i]["text"] for i in gap_idx[:5]]
        new_queries = queries_for_gap(premise, sample)
        state.log.append(f"round {state.rounds}: gap queries {new_queries}")
        grew = _search_and_index(state, new_queries, f"gap-{state.rounds}")
        state.log.append(f"round {state.rounds}: indexed {grew}, size {len(state.store)}")
        if grew < min_growth:
            state.log.append(f"round {state.rounds}: growth below threshold, stopping")
            break
    return state
