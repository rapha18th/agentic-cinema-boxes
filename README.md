# THE BOXES

An autonomous multimodal research agent for film development.

You give it a premise. It runs open-web research on its own, embeds everything it
finds into one space, groups it by meaning, spots the topics it has not covered,
writes its own follow-up searches, and hands back a searchable research library
plus a reference reel.

Built for the Agentic Cinema hackathon, Parallel track.

## How it works

1. **Search.** The premise is split into sub-topics. Each is searched through the
   Parallel Search API.
2. **Embed.** Every article, image, and PDF becomes a vector with Gemini
   Embedding 2. Text, images, and audio share one 3,072-dimension space, so a
   frame and a paragraph are comparable directly.
3. **Group.** Similar vectors fall into the same cluster, so themes form with no
   tags.
4. **Find gaps.** Points at the sparse edge of the covered space mark topics that
   are thin. The loop turns those into new search queries and goes again.
5. **Serve.** Query the index in plain language, or with an image, and get back
   grouped sources. Contradictory findings are flagged.

## Stack

| Part | Choice |
|---|---|
| Agent | Google Agent Development Kit (ADK), graph-native |
| Reasoning | Gemini 3.8 Flash on Vertex AI (`global` location) |
| Embeddings | Gemini Embedding 2, multimodal, 768-dim hot index |
| Vector search | Local brute-force store; Vertex AI Vector Search for scale |
| Partner | Parallel Search API, called on every research pass |
| Runtime | Agent Runtime; Cloud Run for the web UI |

## Setup

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                               # fill in project and Parallel key
gcloud auth application-default login
gcloud auth application-default set-quota-project helenia-11f98
```

Gemini 3.x and Gemini Embedding 2 are served on the Vertex `global` location, so
`GOOGLE_CLOUD_LOCATION=global`.

The Parallel key can go in `.env` for local work, or in Secret Manager as
`PARALLEL_API_KEY`. With no key set, the search client returns a labelled stub so
the pipeline still runs.

## Run

```bash
python scripts/probe_access.py      # confirm model access
python scripts/day2_hello_agent.py  # ADK agent calls Gemini 3.8 Flash
python scripts/day4_embed_nn.py     # multimodal embed + nearest neighbor
python scripts/day5_loop_smoke.py   # the research loop end to end
adk web src/boxes                   # local agent dev UI
```

## Layout

```
src/boxes/
  config.py          environment and Secret Manager access
  embeddings.py       Gemini Embedding 2 helpers, task prefixes, multimodal parts
  vectorstore.py      brute-force nearest neighbor, coverage-gap detection
  parallel_search.py  Parallel Search API client
  agent.py            the ADK agent and its tools
  research_loop.py    the deterministic outer loop
scripts/              day-by-day proofs
```

## License

Apache-2.0. See [LICENSE](LICENSE).
