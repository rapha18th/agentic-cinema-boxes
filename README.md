# THE BOXES

An autonomous multimodal research agent for film development.

Built for the Agentic Cinema hackathon, Parallel track.

## The idea

You give it a film idea. It spends hours doing research on its own, then hands you
an organized, searchable pile of everything it found.

### The problem

Kubrick kept about a thousand boxes of research per film. Clippings, photos,
books, interviews, maps. That pile was his edge. Nobody out-prepared him.
Building it took a team months of library time. A modern director wants the same
pile without the months, and wants it searchable from a phone.

### What you do with it

You type a premise, for example a heist film set in 1929 Vienna during the
hyperinflation. You drop in whatever you already have: a few reference photos, a
piece of music, a paragraph of tone. Then you walk away. Hours later you come
back to a research library you can question in plain language. Show me how banks
looked inside. What did money feel like that year. Find images near this photo I
like. It answers with sources, images, and clips, grouped by theme, and it builds
a rough reference reel from the strongest material.

### How it works

Four steps, on a loop.

1. **Search.** The premise is split into sub-topics: fashion, currency,
   architecture, politics, slang. Each is searched through the Parallel Search
   API.
2. **Embed.** Every article, image, and PDF becomes a meaning fingerprint from
   Gemini Embedding 2. Things that mean similar things get similar numbers. A
   painting of a bank lobby and a paragraph describing one land near each other,
   even though one is a picture and one is text. Images, audio, and text share
   one 3,072-dimension space.
3. **Group.** Similar fingerprints fall into the same pile, so themes form with
   no tags.
4. **Find contradictions.** If one source's text says money was still trusted and
   another source's photo shows people burning it for heat, those two sit close
   in meaning but disagree. The tool flags the pair.

### The coverage map

Picture all that research as dots on a map, where nearby dots mean related ideas.
Dense clusters are topics you have covered. Empty gaps are topics you have not
touched. The tool watches for a gap sitting right next to a dense cluster, which
usually means a real subject you missed.

### It files its own boxes

When it spots one of those gaps, it writes its own new batch of searches, runs
them, and the map fills in. You are not feeding it search terms. It decides what
it still needs to know, and you watch the blank spots disappear. You can also
query the finished index with a single frame or a hummed melody and get back
everything that shares the feeling.

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
python scripts/day3_parallel.py     # live Parallel Search call
python scripts/day4_embed_nn.py     # multimodal embed + nearest neighbor
python scripts/day5_loop_smoke.py   # the research loop end to end
adk web src                         # local agent dev UI at localhost:8000
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
