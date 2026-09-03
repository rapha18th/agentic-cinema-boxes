"""THE BOXES backend.

Wraps the autonomous research loop behind an HTTP API, streams the loop's events
to the browser over SSE, and persists everything under users/{uid} in Firestore
and Cloud Storage.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from boxes import research_loop as rl  # noqa: E402
from boxes import reel as reel_mod  # noqa: E402
from boxes.depth import get as get_depth  # noqa: E402
from boxes.embeddings import embed_texts, embed_parts, image_part, TASK_SEARCH  # noqa: E402
from boxes.evidence import Evidence  # noqa: E402

import auth  # noqa: E402
import store  # noqa: E402

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


# --------------------------------------------------------------------------- #
# run the loop, stream events
# --------------------------------------------------------------------------- #
def _persist_event(uid: str, pid: str, ev: dict) -> None:
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
    elif t == "stop":
        store.set_project_status(uid, pid, status="done", stop_reason=ev["reason"])


def _run_stream(uid: str, pid: str, premise: str, depth: str):
    q: "queue.Queue[dict | None]" = queue.Queue()

    def on_event(ev: dict) -> None:
        q.put(ev)

    def worker() -> None:
        try:
            proj = rl.run(premise, depth=depth, on_event=on_event)
            # persist evidence with 768 vectors
            items = []
            for i, e in enumerate(proj.evidence):
                vec = proj.vectors[i].tolist() if proj.vectors is not None else None
                items.append((e.to_dict(), vec))
            for k in range(0, len(items), 300):
                store.add_evidence_batch(uid, pid, items[k : k + 300])
            beats = reel_mod.build_reel(premise, proj.evidence)
            store.set_reel(uid, pid, [b.to_dict() for b in beats])
            q.put({"type": "reel", "beats": [b.to_dict() for b in beats]})
            q.put({"type": "complete", "confidence": proj.confidence,
                   "evidence": len(proj.evidence), "boxes": len(proj.objectives)})
        except Exception as e:  # noqa: BLE001
            q.put({"type": "error", "error": str(e)})
            store.set_project_status(uid, pid, status="error", error=str(e))
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        ev = q.get()
        if ev is None:
            break
        try:
            _persist_event(uid, pid, ev)
        except Exception:  # noqa: BLE001, S110
            pass
        yield f"data: {json.dumps(ev)}\n\n"


@app.post("/api/projects/{pid}/run")
def run_project(pid: str, uid: str = Depends(auth.current_uid)) -> StreamingResponse:
    p = store.get_project(uid, pid)
    if not p:
        raise HTTPException(404, "not found")
    return StreamingResponse(
        _run_stream(uid, pid, p["premise"], p.get("depth", "scout")),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    order = np.argsort(-sims)[: int(body.get("k", 6))]
    return {
        "matches": [
            {
                "score": round(float(sims[i]), 3),
                "text": rows[i]["text"][:800],
                "citation": _cite(rows[i]),
                "url": rows[i].get("url", ""),
                "image_url": rows[i].get("image_url", ""),
                "media_url": rows[i].get("media_url", ""),
                "media_mime": rows[i].get("media_mime", ""),
                "modality": rows[i].get("modality", "text"),
                "source": rows[i].get("source", "parallel"),
            }
            for i in order
        ]
    }


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
    ctype = file.content_type or "application/octet-stream"
    name = f"{int(time.time())}_{file.filename}"
    path = store.put_file(uid, pid, name, data, ctype)

    if ctype.startswith("image/"):
        vec = embed_parts([image_part(data, ctype)], dim=768)
        text = note or f"[director image] {file.filename}"
        modality = "image"
    else:
        text = (note + "\n\n" + data.decode("utf-8", "ignore"))[:4000].strip()
        vec = embed_texts([text], dim=768)[0]
        modality = "pdf" if ctype == "application/pdf" else "text"

    ev = Evidence(
        text=text, url="", title=file.filename or "director upload",
        source_domain="director", modality=modality, objective_id=objective_id,
        query="director upload", relevance_reason=note, license_note="director-provided",
    )
    d = ev.to_dict()
    d["source"] = "director"
    d["storage_path"] = path
    store.add_evidence(uid, pid, d, vec)
    return {"id": ev.id, "storage_path": path, "modality": modality}
