# THE BOXES

An autonomous research department for filmmakers.

Give it a premise and whatever creative material you already have. It builds a
research plan, searches the live web through Parallel, extracts and indexes
multimodal evidence, measures what it still does not understand, and launches its
own follow-up investigations until the world of the film is covered. The result
is a living, source-backed research archive you can explore with text, images,
documents, audio, or video.

Built for the Agentic Cinema hackathon, Parallel track.

## The idea

You give it a film idea. It does the research on its own, then hands you an
organized, searchable pile of everything it found.

### The problem

Kubrick kept about a thousand boxes of research per film. Clippings, photos,
books, interviews, maps. That pile was his edge. Nobody out-prepared him.
Building it took a team months of library time. A modern director wants the same
pile without the months, and wants it searchable from a phone.

### What you do with it

You type a premise, for example a heist film set in 1929 Vienna during the
hyperinflation. You drop in whatever you already have: a few reference photos, a
piece of music, a paragraph of tone. Then you walk away. You come back to a
research library you can question in plain language. Show me how banks looked
inside. What did money feel like that year. Find images near this photo I like.
It answers with sources grouped by theme, every claim cited, and it cuts a
reference reel from the strongest material.

## How it works

1. **Plan.** Gemini writes a research ontology from the premise: a list of
   objectives, one per "box" (MONEY, BANKING INTERIORS, POLICING, STREETS, SOUND
   and so on). Coverage is measured against this plan, never against empty space.
2. **Acquire.** For each objective, Parallel **Search** finds the right sources
   for a semantic objective, then Parallel **Extract** pulls objective-specific
   content from them. Search plus Extract is the research acquisition engine, not
   a keyword box.
3. **Embed.** Every evidence fragment becomes a vector with Gemini Embedding 2.
   Text, images, PDFs, and audio map into one 3,072-dimension space, so a
   reference photo and an archival photo sit next to each other. A 768 cut is the
   hot index.
4. **Measure.** Per objective: how much evidence supports it and how diverse the
   sources are. Rolled up with source diversity, provenance quality, and an open
   contradiction penalty into a single **research confidence** number.
5. **Verify contradictions.** Embedding similarity finds pairs of evidence about
   the same thing. Gemini then reads both and classifies the relationship as
   supports, contradicts, contextualises, or unrelated, with an explanation and
   both citations. Similarity alone never decides.
6. **Find the next gap.** The thinnest objectives get new queries. If the
   evidence keeps circling a concept with no box, Gemini proposes one and the
   agent opens it.
7. **Stop on its own.** The loop ends when confidence reaches the depth's target,
   or every objective is well covered, or the round budget runs out.

```text
                      ┌──────────────┐
                      │ FILM PREMISE │
                      │ + REFERENCES │
                      └──────┬───────┘
                             ▼
                   ┌──────────────────┐
                   │ GEMINI 3.8 FLASH │  research plan / ontology
                   └────────┬─────────┘
                            ▼
                   ┌──────────────────┐
                   │     PARALLEL     │  Search  ->  Extract
                   └────────┬─────────┘
                            ▼  evidence units
                 ┌────────────────────────┐
                 │   GEMINI EMBEDDING 2    │  one multimodal space
                 └───────────┬────────────┘
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
          CLUSTERS     CONTRADICTIONS     COVERAGE
              │        (Gemini verdicts)  (per objective)
              └──────────────┼───────────────┘
                             ▼
                    RESEARCH CONFIDENCE
                     below target?
                             │ yes
                       next objective ─────────► PARALLEL
                             │ no
                            done
```

## Research depth

The same agent, tuned for how hard it digs. `scout` runs in a couple of minutes
for a demo. `kubrick` is the obsessive setting.

| Depth | Objectives | Rounds | Confidence target |
|---|---:|---:|---:|
| scout | 5 | 1 | 60% |
| production | 10 | 3 | 82% |
| kubrick | 16 | 6 | 90% |

## Stack

| Part | Choice |
|---|---|
| Agent | Google Agent Development Kit (ADK) on the Gemini Enterprise Agent Platform |
| Reasoning | Gemini 3.8 Flash (GA 2 September 2026, `gemini-3.8-flash`, built for agentic multi-step reasoning), on Vertex AI `global` location |
| Acquisition | Parallel Search plus Parallel Extract, on the hot path every round |
| Embeddings | Gemini Embedding 2, multimodal, 3,072-dim stored, 768-dim hot index |
| Vector search | Local brute-force store; Vertex AI Vector Search for scale |
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
`PARALLEL_API_KEY`.

## Run

```bash
python scripts/probe_access.py       # confirm model access
python scripts/day2_hello_agent.py   # ADK agent calls Gemini 3.8 Flash
python scripts/day3_parallel.py      # live Parallel Search call
python scripts/day4_embed_nn.py      # multimodal embed + nearest neighbor
python scripts/research_run.py scout  # the full loop: plan, acquire, cover, verify, stop
adk web src                          # local agent dev UI at localhost:8000
```

## Layout

```
src/boxes/
  config.py           environment and Secret Manager access
  llm.py              shared Gemini client, JSON reasoning calls
  embeddings.py       Gemini Embedding 2 helpers, task prefixes, multimodal parts
  evidence.py         the evidence unit, with full provenance
  ontology.py         research plan and emergent-gap detection
  parallel_search.py  Parallel Search + Extract -> evidence
  coverage.py         per-objective coverage and research confidence
  contradiction.py    embedding candidates, Gemini verdicts
  depth.py            scout / production / kubrick presets
  ledger.py           the visible research ledger
  reel.py             the reference reel
  research_loop.py     the autonomous loop, with an event stream
  agent.py            the ADK agent and its tools
  vectorstore.py      brute-force nearest neighbor (swap for Vertex Vector Search)
scripts/              proofs and the full run
```

## License

Apache-2.0. See [LICENSE](LICENSE).
