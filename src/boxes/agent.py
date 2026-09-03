"""The ADK agent for THE BOXES.

`root_agent` is a graph-native ADK agent on Gemini 3.8 Flash. It has two tools:
one that runs a Parallel web search, one that embeds and indexes what it finds
with Gemini Embedding 2. The deterministic outer research loop lives in
`research_loop.py`; this agent is the reasoning node inside it and the surface
`adk web` talks to.
"""

from __future__ import annotations

from google.adk.agents import Agent

from . import config
from . import parallel_search as ps
from .embeddings import TASK_SEARCH, embed_texts
from .vectorstore import VectorStore

_STORE = VectorStore(dim=768)


def parallel_search(query: str, max_results: int = 8) -> dict:
    """Search the open web through the Parallel Search API.

    Args:
        query: A focused research question or phrase.
        max_results: How many hits to return (1-20).

    Returns:
        A dict with a "hits" list of {title, url, text, image_url}.
    """
    hits = ps.search(query, max_results=max_results)
    return {
        "hits": [
            {"title": h.title, "url": h.url, "text": h.text[:1200], "image_url": h.image_url}
            for h in hits
        ],
        "used_stub": not ps.has_key(),
    }


def index_findings(texts: list[str], topic: str) -> dict:
    """Embed a batch of findings with Gemini Embedding 2 and add them to the
    research index.

    Args:
        texts: Snippets to index.
        topic: The sub-topic these snippets belong to.

    Returns:
        A dict with the new index size and the count added.
    """
    vecs = embed_texts(texts, dim=768)
    _STORE.add(vecs, [{"topic": topic, "text": t[:500]} for t in texts])
    return {"indexed": len(texts), "index_size": len(_STORE)}


def query_index(question: str, k: int = 6) -> dict:
    """Search the research index for the passages nearest a question."""
    qv = embed_texts([question], dim=768, prefix=TASK_SEARCH)[0]
    return {
        "matches": [
            {"score": round(s, 3), "topic": m["topic"], "text": m["text"]}
            for s, m in _STORE.search(qv, k=k)
        ]
    }


root_agent = Agent(
    model=config.CHAT_MODEL,
    name="boxes",
    description="Autonomous multimodal research agent for film development.",
    instruction=(
        "You are THE BOXES, a research daemon for filmmakers. Given a premise, "
        "break it into concrete sub-topics, call parallel_search on each, then "
        "call index_findings with the useful snippets. When asked a question, "
        "call query_index and answer only from what it returns, citing titles. "
        "Be concrete and terse. Flag any two findings that contradict each other."
    ),
    tools=[parallel_search, index_findings, query_index],
)


def store() -> VectorStore:
    return _STORE
