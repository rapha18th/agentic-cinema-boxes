# THE BOXES

An autonomous research department for filmmakers.

Give it a film premise and whatever creative material you already have. It builds
a research plan, searches the live web through Parallel, extracts and embeds
multimodal evidence, measures what it still does not understand, opens its own
follow-up boxes, and stops when the planned research is sufficiently complete. It also surveys existing films
for a similar premise and states where this one is still unclaimed. The result
is a living, source-backed research archive you can explore with text, images,
documents, audio, or video, or read as a self-contained PDF dossier.

Built for the Agentic Cinema hackathon, Parallel track.

Deployed on Firebase Hosting (frontend) and Cloud Run (backend) under a Google
Cloud project. Configure your own with `.env` / `web/.env` / `.firebaserc`
(see the `*.example` files).

![Architecture](docs/architecture.png)

## The idea

Kubrick kept about a thousand boxes of research per film. Clippings, photos,
books, interviews, maps. That pile was his edge, and building it took a team
months of library time. THE BOXES gives every filmmaker the same pile, built
overnight, searchable from a phone. A public, read-only judge dossier at `/demo`
shows the complete experience without requiring an account.

You type a premise, drop in a few references, and walk away. You come back to a
research library you can question in plain language, with every claim cited, plus
a reference reel cut from the strongest material.

## How the loop works

The production API runs the deterministic loop through a custom Google Agent
Development Kit `BaseAgent` on Cloud Run. The loop's control flow is plain,
concurrent Python. Objectives research in parallel,
contradiction checks and embeddings verify concurrently, and ADK exposes the
whole thing as a conversational tool surface (`plan_research`, `run_research`,
`query_index`, ...). Every step streams to the browser as it happens.

1. **PLAN.** Gemini 3.8 Flash writes a research ontology from the premise: a list
   of objectives, one per box, each tagged with the production departments it
   would brief. Coverage is measured against this plan.
2. **ACQUIRE.** One call writes the round's search queries for every objective
   at once. Objectives then research concurrently: Parallel **Search** finds
   sources for each one, Parallel **Extract** pulls objective-specific full
   text, and the pages it surfaces are mined for pictures, PDFs, audio, and
   video. Audio and video are trimmed to a short clip with ffmpeg.
3. **EMBED.** Every fragment, text or image or PDF or audio or video, becomes a
   vector with Gemini Embedding 2, embedded concurrently. One normalized
   768-dimensional multimodal index. A reference photo and an
   archival photo sit next to each other; a needle-drop sits next to a
   paragraph.
4. **MEASURE.** Per objective: how much evidence supports it and how diverse the
   sources are. Rolled up with source diversity, a visible deterministic
   source-quality score, and a genuine-contradiction penalty into **research completeness**.
5. **VERIFY.** Embedding similarity finds pairs of evidence about the same thing.
   Gemini then reads both and classifies the relationship as supports,
   contradicts, contextualises, or unrelated, with an explanation and both
   citations, all candidate pairs verified concurrently. Similarity alone
   never decides.
6. **GAP.** The thinnest objectives get fresh queries. If the evidence keeps
   circling a concept with no box, Gemini proposes one and the agent opens it.

The loop ends on its own when completeness reaches the depth's target, or every
objective is well covered, or the round budget runs out.

A run holds a Firestore lease keyed to its own id, so two clicks or two tabs
cannot start competing writers, and a dropped SSE stream reattaches to the run
already in progress. The stale-after window releases a lease whose worker died.

## Prior art

On request, THE BOXES surveys existing films for a similar premise. TMDB
supplies the candidate pool through its free developer API; IMDb licenses
its data as an enterprise product on AWS Data Exchange. One Parallel Search
pass broadens past TMDB's own tagging, and Gemini Embedding 2 ranks every
candidate against the premise by meaning, so a heist "without entering the
vault" finds its real neighbours whatever genre tag it carries. Gemini then
reads the closest films and states which angles none of them take, always
naming which titles that claim was checked against. Originality is claimed
only relative to the surveyed set.

## The multimodal space

Parallel Search returns text. To make Gemini Embedding 2 earn its place, THE
BOXES harvests the other modalities from the pages Parallel surfaces:

| Modality | Where it comes from | Embedded as |
|---|---|---|
| text | Parallel Extract full content | text |
| image | og:image and substantive inline images | picture + caption |
| pdf | links ending `.pdf`, fetched whole (`%PDF-`, up to 12 MB) | document + caption |
| audio | `<audio>`, og:audio, direct `.mp3` / `.wav` / `.m4a` links | ffmpeg-trimmed clip + caption |
| video | `<video>`, og:video, direct `.mp4` / `.webm` links | ffmpeg-trimmed clip + caption |

Every asset keeps its full source URL and a conservative rights note (`open-access
host · verify item rights` for known archives; `rights not verified` otherwise).
Trimmed clips link back to the full recording at its source.

Text, images, and PDFs harvest reliably. Audio and video depend on the source
page exposing a directly fetchable file: many of the hosts that carry open
recordings put them behind a player or block a server-side fetch. Harvest fetches
now use a browser user agent and accept archive downloads served as
`octet-stream`, which widens the set of pages that yield a clip. A headless fetch
or an archive.org API path would close the rest of the gap.

## The app

The project page opens on the outcome. A metric row (readiness, evidence,
primary records, open risks) sits above five tabs. `Project.tsx` (live) and
`Demo.tsx` (a frozen run) render the same tab set from `web/src/workspace/tabs.tsx`.

| Tab | What it holds |
|---|---|
| **Overview** | The synthesized picture of the world, the strongest evidence, the thinnest boxes, a reference-sequence outline, and a grounded Ask box that answers from the index and abstains when the archive is thin. |
| **Departments** | One expandable packet per crew (script, casting, costume, art direction, sound, cinematography, locations). Each opens to its boxes, their plain-language summaries, and their evidence, with images, PDFs, audio and video rendered in place. |
| **Evidence** | The research map plus an All / department filter. A dot per fragment, positioned relative to its own box; images are thumbnails, other media are glyphs. Click a box to focus it, a dot to open it in a detail modal. Contradicted fragments carry a ring on the map, a tag on the card, and a panel in the modal. Zoom, pan, full screen. "Add your own reference" sits at the top: upload a text, PDF, or image and it embeds alongside the agent's findings. |
| **Trace** | The cinematic console while a run is active (phase headline, block-character bars, teletype log), then a decision timeline (planned, per round, opened a box, cross-examined, stopped), the expandable per-pass ledger with its queries, and the verified contradiction verdicts. |
| **Prior art** | Survey on demand. A poster grid of the closest existing films with each one's description and similarity, then the angles none of them take, each naming the titles it was checked against. |

`/demo` is a genuine production run frozen to a static file: no account, no
Firebase on the page, the same five tabs, and a downloadable PDF dossier.
Theme (light, dark, system) applies everywhere, including the landing page.
Evidence and progress persist to Firestore as they stream, so a live run's
map and counts fill in as it works.

## Research depth

The same agent, tuned for how hard it digs. The cinematic names stay visible;
hover or keyboard-focus a depth in the app to reveal runtime, relative API spend,
and expected output.

| Depth | Typical time | Relative cost | Objectives | Follow-up rounds | Completeness target | Images / PDFs / A-V per round |
|---|---:|---:|---:|---:|---:|---:|
| scout | 2–4 min | 1× | 5 | up to 2 | 80% | 4 / 2 / 2 |
| production | 6–12 min | 3× | 10 | up to 3 | 82% | 10 / 5 / 4 |
| kubrick | 15–30 min | 8× | 16 | up to 6 | 90% | 20 / 10 / 8 |

## Stack

| Part | Choice |
|---|---|
| Agent | A custom Google ADK `BaseAgent` is the production workflow entry point on Cloud Run; the conversational ADK tool surface uses the same loop |
| Reasoning | Gemini 3.8 Flash (`gemini-3.8-flash`, GA 2 September 2026), Vertex AI `global` location |
| Acquisition | Parallel **Search** + **Extract** APIs, called on the hot path in every round |
| Prior art | TMDB for the candidate pool, Parallel Search to broaden past its tagging |
| Embeddings | Gemini Embedding 2 (`gemini-embedding-2`), natively multimodal, using a normalized 768-dimensional index stored separately from browser-facing evidence metadata |
| Frontend | Vite + React, Firebase Hosting |
| Auth | Firebase Authentication (Google), one isolated project subtree per user |
| Persistence | Cloud Firestore (`users/{uid}/…`), Cloud Storage for source files and uploads |
| Backend | FastAPI on Cloud Run, verifies Firebase ID tokens, streams the loop over SSE |
| Report | reportlab, one Gemini call synthesizes the plain-language narrative, Pillow for embedded moodboard images |
| Media | ffmpeg in the container, trims harvested audio and video before embedding |
| Vector search | brute-force over the stored 768-d vectors; swap for Vertex AI Vector Search at scale |

## Repo layout

```
src/boxes/
  config.py           environment + Secret Manager
  llm.py              shared Gemini client, JSON reasoning (thinking disabled)
  embeddings.py       Gemini Embedding 2 helpers, task prefixes, multimodal parts
  evidence.py         the evidence unit: provenance, modality, media URL, round, vector
  ontology.py         research plan + emergent-box detection, batched per round
  parallel_search.py  Parallel Search + Extract, plus image/pdf/audio/video harvest
  media.py            ffmpeg trims audio/video to a short clip
  coverage.py         per-objective coverage + research completeness + stopping rule
  contradiction.py    embedding candidate pairs, Gemini verdicts, verified concurrently
  prior_art.py        TMDB + Parallel candidate pool, embedding-ranked, Gemini positioning
  synthesis.py        plain-language narrative for the PDF report, box by box
  depth.py            scout / production / kubrick presets
  ledger.py           the per-round research ledger
  reel.py             the reference reel
  qa.py               grounded answer over retrieved fragments, with abstention
  workflow.py         custom ADK BaseAgent, the production API's entry point
  research_loop.py    the autonomous loop; objectives research concurrently each round
  agent.py            the conversational ADK tool surface over the same loop
  vectorstore.py      brute-force nearest neighbor
service/              FastAPI backend for Cloud Run (auth, SSE, Firestore/Storage, report.py the PDF dossier)
web/src/workspace/    the shared tab set both Project.tsx and Demo.tsx render
web/                  Vite + React app (results-first dossier, map, console, ledger, reel, theme)
docs/architecture.py  the diagram source
scripts/
  probe_access.py     confirm model access
  research_run.py     one research run, printed to the console
  snapshot_demo.py    run end to end and freeze web/public/demo-snapshot.json
  clean_snapshot.py   drop polluting sources, build the demo PDF, flag style slips
```

## Run it locally

Backend and models:

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r service/requirements.txt
cp .env.example .env                               # project id + Parallel key
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_GCP_PROJECT
```

Gemini 3.x and Gemini Embedding 2 are served on the Vertex `global` location, so
`GOOGLE_CLOUD_LOCATION=global`. The Parallel key goes in `.env` as
`PARALLEL_API_KEY`, or in Secret Manager under the same name. `TMDB_API_KEY`
is optional and takes TMDB's v3 API key; the longer v4 read access token will
not authenticate. Without it, prior art still runs on Parallel Search alone,
with a thinner pool.

```bash
python scripts/probe_access.py           # confirm model access
python scripts/research_run.py scout "A political drama during the founding of NASA in 1958"
python -m unittest discover -s tests -v  # deterministic core checks
adk web src                              # local ADK dev UI at localhost:8000

# full stack
BOXES_DEV_UID=dev uvicorn main:app --app-dir service --port 8080   # backend
cd web && npm install && npm run dev                               # frontend on :5173
```

## Deploy

```bash
# backend
gcloud run deploy boxes-api --source . --project YOUR_GCP_PROJECT --region us-central1 \
  --service-account boxes-agent@YOUR_GCP_PROJECT.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,FIREBASE_STORAGE_BUCKET=YOUR_GCP_PROJECT.firebasestorage.app \
  --set-secrets PARALLEL_API_KEY=PARALLEL_API_KEY:latest,TMDB_API_KEY=TMDB_API_KEY:latest \
  --allow-unauthenticated --cpu 2 --memory 2Gi --timeout 3600 --max-instances 3

# rules + frontend
firebase deploy --only firestore:rules,storage --project YOUR_GCP_PROJECT
cd web && npm run build && cd .. && firebase deploy --only hosting --project YOUR_GCP_PROJECT
```

## License

Apache-2.0. See [LICENSE](LICENSE).
