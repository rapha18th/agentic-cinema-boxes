"""THE BOXES backend.

Wraps the autonomous research loop behind an HTTP API, streams the loop's events
to the browser over SSE, and persists everything under users/{uid} in Firestore
and Cloud Storage.
"""

from __future__ import annotations

import json
import io
import os
import queue
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from google.genai import types
from pypdf import PdfReader
from PIL import Image
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from boxes.workflow import workflow_agent  # noqa: E402
from boxes import reel as reel_mod  # noqa: E402
from boxes.depth import get as get_depth  # noqa: E402
from boxes.embeddings import embed_texts, embed_parts, image_part, TASK_SEARCH  # noqa: E402
from boxes.evidence import Evidence  # noqa: E402
from boxes import prior_art as prior_art_mod  # noqa: E402
from boxes import qa as qa_mod  # noqa: E402
from boxes import synthesis as synthesis_mod  # noqa: E402

import auth  # noqa: E402
import report  # noqa: E402
import store  # noqa: E402

_DEPTHS = {"scout", "production", "kubrick"}
_MAX_UPLOAD = 12 * 1024 * 1024
_UPLOAD_TYPES = {"text/plain", "application/pdf", "image/png", "image/jpeg", "image/webp"}

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]  # required
BUCKET = os.environ.get("FIREBASE_STORAGE_BUCKET", f"{PROJECT_ID}.firebasestorage.app")

store.init(PROJECT_ID, BUCKET)

app = FastAPI(title="THE BOXES")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BOXES_CORS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "project": PROJECT_ID}


@app.get("/api/projects")
def list_projects(uid: str = Depends(auth.current_uid)) -> dict:
    return {"projects": store.list_projects(uid)}


@app.post("/api/projects")
def create_project(body: dict, uid: str = Depends(auth.current_uid)) -> dict:
    premise = (body.get("premise") or "").strip()
    depth = body.get("depth", "scout")
    if not premise:
        raise HTTPException(400, "premise required")
    if depth not in _DEPTHS:
        raise HTTPException(400, "depth must be scout, production or kubrick")
    pid = uuid.uuid4().hex[:12]
    store.create_project(uid, pid, premise, depth)
    return {"id": pid, "premise": premise, "depth": depth}


@app.get("/api/projects/{pid}")
def get_project(pid: str, uid: str = Depends(auth.current_uid)) -> dict:
    p = store.get_project(uid, pid)
    if not p:
        raise HTTPException(404, "not found")
    p["id"] = pid
    return p


@app.patch("/api/projects/{pid}")
def update_project(pid: str, body: dict, uid: str = Depends(auth.current_uid)) -> dict:
    if not store.get_project(uid, pid):
        raise HTTPException(404, "not found")
    patch: dict = {}
    if "premise" in body:
        premise = (body.get("premise") or "").strip()
        if not premise:
            raise HTTPException(400, "premise cannot be empty")
        patch["premise"] = premise
    if "depth" in body:
        depth = body.get("depth")
        if depth not in _DEPTHS:
            raise HTTPException(400, "depth must be scout, production or kubrick")
        patch["depth"] = depth
    if not patch:
        raise HTTPException(400, "nothing to update")
    store.update_project(uid, pid, **patch)
    return {"id": pid, **patch}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, uid: str = Depends(auth.current_uid)) -> dict:
    if not store.get_project(uid, pid):
        raise HTTPException(404, "not found")
    store.delete_project(uid, pid)
    return {"deleted": pid}


@app.get("/api/projects/{pid}/report.pdf")
def project_report(pid: str, uid: str = Depends(auth.current_uid)) -> Response:
    p = store.get_project(uid, pid)
    if not p:
        raise HTTPException(404, "not found")
    p["id"] = pid
    pdf = report.build_report_pdf(
        project=p,
        boxes=store.list_boxes(uid, pid),
        evidence=store.list_evidence_report(uid, pid),
        verdicts=store.list_verdicts(uid, pid),
        runs=store.list_runs(uid, pid),
        reel=store.get_reel(uid, pid),
        prior_art=store.get_prior_art(uid, pid),
    )
    stub = "".join(c if c.isalnum() else "-" for c in (p.get("premise") or "boxes"))[:40].strip("-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="the-boxes-{stub or pid}.pdf"'},
    )


# --------------------------------------------------------------------------- #
# run the loop, stream events
# --------------------------------------------------------------------------- #
def _persist_event(uid: str, pid: str, ev: dict, run_id: str = "") -> None:
    t = ev.get("type")
    if t == "plan":
        store.upsert_boxes(uid, pid, [{**o, "score": 0.0, "evidence_count": 0} for o in ev["objectives"]])
        store.set_project_status(uid, pid, status="researching")
    elif t == "emergent_gap":
        o = ev["objective"]
        store.upsert_box(uid, pid, {**o, "score": 0.0, "evidence_count": 0})
    elif t == "coverage":
        rep = ev["report"]
        for c in rep["per_objective"]:
            store.upsert_box(uid, pid, {
                "id": c["id"], "score": c["score"],
                "evidence_count": c["evidence_count"], "distinct_domains": c["distinct_domains"],
            })
        store.set_project_status(
            uid, pid, confidence=rep["confidence"], coverage=rep["overall_coverage"],
            source_diversity=rep["source_diversity"], provenance_quality=rep["provenance_quality"],
            unresolved_contradictions=rep["unresolved_contradictions"],
        )
    elif t == "contradiction":
        store.add_verdict(uid, pid, ev["verdict"])
    elif t == "round_done":
        store.add_run(uid, pid, ev["record"])
    elif t == "evidence":
        # write as it arrives so the map fills live; vectors added at the end
        store.add_evidence_batch(uid, pid, [(it, None) for it in ev["items"]])
    elif t == "progress":
        store.set_project_status(uid, pid, progress={k: v for k, v in ev.items() if k != "type"})
        if run_id:
            store.touch_run(uid, pid, run_id)
    elif t == "stop":
        store.set_project_status(uid, pid, status="done", stop_reason=ev["reason"])


def _run_stream(uid: str, pid: str, premise: str, depth: str, run_id: str):
    q: "queue.Queue[dict | None]" = queue.Queue()

    def on_event(ev: dict) -> None:
        ev["run_id"] = run_id
        try:
            _persist_event(uid, pid, ev, run_id)
        except Exception:  # noqa: BLE001, S110
            pass
        q.put(ev)

    def worker() -> None:
        try:
            proj = workflow_agent.execute(premise, depth=depth, on_event=on_event)
            # persist evidence with 768 vectors
            coords = _semantic_coordinates(proj.vectors)
            items = []
            for i, e in enumerate(proj.evidence):
                vec = proj.vectors[i].tolist() if proj.vectors is not None else None
                doc = e.to_dict()
                if i < len(coords):
                    doc["map_x"], doc["map_y"] = coords[i]
                items.append((doc, vec))
            # Two writes per item (metadata + private vector), kept below the
            # Firestore 500-operation batch limit.
            for k in range(0, len(items), 200):
                store.add_evidence_batch(uid, pid, items[k : k + 200])
            beats = reel_mod.build_reel(premise, proj.evidence)
            store.set_reel(uid, pid, [b.to_dict() for b in beats])
            try:
                narrative = synthesis_mod.build(
                    premise,
                    [o.to_dict() for o in proj.objectives],
                    [e.to_dict() for e in proj.evidence],
                )
                if narrative.overview:
                    store.set_project_status(uid, pid, overview=narrative.overview)
                for objective in proj.objectives:
                    summary = narrative.box_summaries.get(objective.id)
                    if summary:
                        store.upsert_box(uid, pid, {"id": objective.id, "summary": summary})
            except Exception:  # noqa: BLE001, S110
                pass
            q.put({"type": "reel", "beats": [b.to_dict() for b in beats]})
            q.put({"type": "complete", "confidence": proj.confidence,
                   "evidence": len(proj.evidence), "boxes": len(proj.objectives)})
        except Exception as e:  # noqa: BLE001
            q.put({"type": "error", "error": str(e)})
            store.set_project_status(uid, pid, status="error", error=str(e))
        finally:
            store.finish_run(uid, pid, run_id)
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        ev = q.get()
        if ev is None:
            break
        yield f"data: {json.dumps(ev)}\n\n"


def _semantic_coordinates(vectors: np.ndarray | None) -> list[tuple[float, float]]:
    """Project embeddings into a stable two-dimensional evidence space."""
    if vectors is None or len(vectors) == 0:
        return []
    mat = np.asarray(vectors, dtype=np.float32)
    if len(mat) == 1:
        return [(0.5, 0.5)]
    centered = mat - mat.mean(axis=0, keepdims=True)
    try:
        u, s, _ = np.linalg.svd(centered, full_matrices=False)
        xy = u[:, :2] * s[:2]
    except np.linalg.LinAlgError:
        return [(0.5, 0.5) for _ in range(len(mat))]
    if xy.shape[1] == 1:
        xy = np.column_stack([xy[:, 0], np.zeros(len(xy))])
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    scaled = (xy - lo) / np.maximum(hi - lo, 1e-9)
    scaled = 0.08 + scaled * 0.84
    return [(round(float(x), 5), round(float(y), 5)) for x, y in scaled]


@app.post("/api/projects/{pid}/run")
def run_project(pid: str, uid: str = Depends(auth.current_uid)) -> StreamingResponse:
    p = store.get_project(uid, pid)
    if not p:
        raise HTTPException(404, "not found")
    run_id = uuid.uuid4().hex[:16]
    if not store.try_start_run(uid, pid, run_id):
        raise HTTPException(409, "a research run is already active for this project")
    return StreamingResponse(
        _run_stream(uid, pid, p["premise"], p.get("depth", "scout"), run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Run-Id": run_id},
    )


# --------------------------------------------------------------------------- #
# prior art: where this premise sits against films that already exist
# --------------------------------------------------------------------------- #
_prior_art_locks: dict[str, threading.Lock] = {}
_prior_art_guard = threading.Lock()


def _prior_art_lock(key: str) -> threading.Lock:
    with _prior_art_guard:
        return _prior_art_locks.setdefault(key, threading.Lock())


@app.post("/api/projects/{pid}/prior-art")
def survey_prior_art(pid: str, uid: str = Depends(auth.current_uid)) -> dict:
    p = store.get_project(uid, pid)
    if not p:
        raise HTTPException(404, "not found")
    # One survey per project at a time. A second click, another tab, or a
    # future auto-trigger during the research loop gets 409 instead of racing
    # a duplicate survey and clobbering the stored result.
    lock = _prior_art_lock(f"{uid}/{pid}")
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "a prior-art survey is already running for this project")
    try:
        report_data = prior_art_mod.survey(p["premise"]).to_dict()
        store.set_prior_art(uid, pid, report_data)
        return report_data
    finally:
        lock.release()


@app.get("/api/projects/{pid}/prior-art")
def get_prior_art(pid: str, uid: str = Depends(auth.current_uid)) -> dict:
    if not store.get_project(uid, pid):
        raise HTTPException(404, "not found")
    return store.get_prior_art(uid, pid) or {}


# --------------------------------------------------------------------------- #
# ask the index
# --------------------------------------------------------------------------- #
@app.post("/api/projects/{pid}/ask")
def ask(pid: str, body: dict, uid: str = Depends(auth.current_uid)) -> dict:
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question required")
    rows = [r for r in store.list_evidence(uid, pid) if r.get("vector768")]
    if not rows:
        raise HTTPException(409, "no research yet")
    mat = np.asarray([r["vector768"] for r in rows], dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    qv = np.asarray(embed_texts([question], dim=768, prefix=TASK_SEARCH)[0], dtype=np.float32)
    qv /= np.linalg.norm(qv) + 1e-9
    sims = mat @ qv
    order = np.argsort(-sims)[: min(8, max(3, int(body.get("k", 6))))]
    matches = [
            {
                "id": rows[i].get("id", ""),
                "score": round(float(sims[i]), 3),
                "text": rows[i]["text"][:800],
                "citation": _cite(rows[i]),
                "url": rows[i].get("url", ""),
                "image_url": rows[i].get("image_url", ""),
                "media_url": rows[i].get("media_url", ""),
                "media_mime": rows[i].get("media_mime", ""),
                "modality": rows[i].get("modality", "text"),
                "source": rows[i].get("source", "parallel"),
                "source_domain": rows[i].get("source_domain", ""),
                "title": rows[i].get("title", ""),
                "publish_date": rows[i].get("publish_date"),
                "source_tier": rows[i].get("source_tier", "web"),
                "quality_score": rows[i].get("quality_score", 0.0),
            }
            for i in order
        ]
    grounded = qa_mod.answer(question, matches, [m["score"] for m in matches])
    cited = grounded.pop("cited_indices")
    sources = [matches[i - 1] for i in cited]
    return {**grounded, "sources": sources, "matches": matches}


def _cite(row: dict) -> str:
    bits = [row.get("title") or row.get("source_domain") or row.get("url", "")]
    if row.get("source_domain") and row["source_domain"] not in bits[0]:
        bits.append(row["source_domain"])
    if row.get("publish_date"):
        bits.append(row["publish_date"])
    return " · ".join(b for b in bits if b)


# --------------------------------------------------------------------------- #
# director adds a resource to a box (B1 continuity slice)
# --------------------------------------------------------------------------- #
@app.post("/api/projects/{pid}/resources")
async def add_resource(
    pid: str,
    file: UploadFile,
    objective_id: str = "",
    note: str = "",
    uid: str = Depends(auth.current_uid),
) -> dict:
    if not store.get_project(uid, pid):
        raise HTTPException(404, "not found")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, "upload exceeds the 12 MB limit")
    ctype = (file.content_type or "application/octet-stream").lower().split(";", 1)[0]
    if ctype not in _UPLOAD_TYPES:
        raise HTTPException(415, "supported uploads: text, PDF, PNG, JPEG and WebP")
    if objective_id and objective_id not in {b.get("id") for b in store.list_boxes(uid, pid)}:
        raise HTTPException(400, "unknown research box")
    original = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file.filename or "reference").name)[:120]
    name = f"{int(time.time())}_{original or 'reference'}"

    if ctype == "application/pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(400, "file does not appear to be a PDF")
    if ctype.startswith("image/"):
        try:
            im = Image.open(io.BytesIO(data))
            im.verify()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "file does not appear to be a valid image") from exc
    path = store.put_file(uid, pid, name, data, ctype)

    if ctype.startswith("image/"):
        vec = embed_parts([image_part(data, ctype)], dim=768)
        text = note or f"[director image] {file.filename}"
        modality = "image"
    elif ctype == "application/pdf":
        vec = embed_parts([types.Part.from_bytes(data=data, mime_type=ctype)], dim=768)
        try:
            reader = PdfReader(io.BytesIO(data))
            extracted = "\n".join((page.extract_text() or "") for page in reader.pages[:20])
        except Exception:  # noqa: BLE001
            extracted = ""
        text = (note + "\n\n" + extracted).strip()[:8000] or f"[director PDF] {file.filename}"
        modality = "pdf"
    else:
        text = (note + "\n\n" + data.decode("utf-8", "replace"))[:8000].strip()
        vec = embed_texts([text], dim=768)[0]
        modality = "text"

    ev = Evidence(
        text=text, url="", title=file.filename or "director upload",
        source_domain="director", modality=modality, objective_id=objective_id,
        query="director upload", relevance_reason=note, license_note="director-provided",
        source_tier="director", quality_score=0.85,
    )
    d = ev.to_dict()
    d["source"] = "director"
    d["storage_path"] = path
    store.add_evidence(uid, pid, d, vec)
    return {"id": ev.id, "storage_path": path, "modality": modality}
