"""Firestore + Cloud Storage persistence.

Every document and file lives under users/{uid}. The backend writes with the
Admin SDK; clients read their own subtree through security rules and never write.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

import firebase_admin
from firebase_admin import firestore, storage

_app: firebase_admin.App | None = None


def init(project_id: str, bucket: str) -> None:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app(
            options={"projectId": project_id, "storageBucket": bucket}
        )


def db() -> firestore.Client:
    return firestore.client()


def bucket():
    return storage.bucket()


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def _proj_ref(uid: str, pid: str):
    return db().collection("users").document(uid).collection("projects").document(pid)


# --------------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------------- #
def create_project(uid: str, pid: str, premise: str, depth: str) -> None:
    _proj_ref(uid, pid).set(
        {
            "premise": premise,
            "depth": depth,
            "status": "created",
            "confidence": 0.0,
            "coverage": 0.0,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    )


def set_project_status(uid: str, pid: str, **fields: Any) -> None:
    fields["updated_at"] = time.time()
    _proj_ref(uid, pid).set(fields, merge=True)


def update_project(uid: str, pid: str, **fields: Any) -> None:
    """Edit user-owned fields (premise, depth). Same shape as set_project_status
    but named for intent."""
    fields["updated_at"] = time.time()
    _proj_ref(uid, pid).set(fields, merge=True)


def try_start_run(uid: str, pid: str, run_id: str, stale_after: float = 7200) -> bool:
    """Acquire a cross-instance Firestore lease for a research run."""
    ref = _proj_ref(uid, pid)
    transaction = db().transaction()

    @firestore.transactional
    def claim(txn) -> bool:
        snap = ref.get(transaction=txn)
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        active = data.get("active_run_id")
        touched = float(data.get("run_updated_at") or 0)
        if active and time.time() - touched < stale_after:
            return False
        txn.set(ref, {
            "active_run_id": run_id, "run_updated_at": time.time(),
            "status": "researching", "error": firestore.DELETE_FIELD,
            "updated_at": time.time(),
        }, merge=True)
        return True

    return claim(transaction)


def touch_run(uid: str, pid: str, run_id: str) -> None:
    ref = _proj_ref(uid, pid)
    snap = ref.get()
    if snap.exists and (snap.to_dict() or {}).get("active_run_id") == run_id:
        ref.set({"run_updated_at": time.time(), "updated_at": time.time()}, merge=True)


def finish_run(uid: str, pid: str, run_id: str) -> None:
    ref = _proj_ref(uid, pid)
    transaction = db().transaction()

    @firestore.transactional
    def release(txn) -> None:
        snap = ref.get(transaction=txn)
        if snap.exists and (snap.to_dict() or {}).get("active_run_id") == run_id:
            txn.set(ref, {
                "active_run_id": firestore.DELETE_FIELD,
                "run_updated_at": firestore.DELETE_FIELD,
                "updated_at": time.time(),
            }, merge=True)

    release(transaction)


def get_project(uid: str, pid: str) -> dict | None:
    snap = _proj_ref(uid, pid).get()
    return snap.to_dict() if snap.exists else None


def _delete_collection(col, batch_size: int = 300) -> None:
    while True:
        docs = list(col.limit(batch_size).stream())
        if not docs:
            return
        batch = db().batch()
        for d in docs:
            batch.delete(d.reference)
        batch.commit()


def delete_project(uid: str, pid: str) -> None:
    """Remove the project doc, every subcollection under it, and its files."""
    ref = _proj_ref(uid, pid)
    client = db()
    try:
        client.recursive_delete(ref)  # google-cloud-firestore >= 2.5
    except AttributeError:
        for sub in ("boxes", "evidence", "vectors", "runs", "verdicts", "meta"):
            _delete_collection(ref.collection(sub))
    ref.delete()  # idempotent belt-and-braces
    try:
        for blob in bucket().list_blobs(prefix=f"users/{uid}/projects/{pid}/"):
            blob.delete()
    except Exception:  # noqa: BLE001, S110
        pass


def list_projects(uid: str) -> list[dict]:
    out = []
    for d in (
        db().collection("users").document(uid).collection("projects")
        .order_by("created_at", direction=firestore.Query.DESCENDING).stream()
    ):
        row = d.to_dict()
        row["id"] = d.id
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# boxes / evidence / runs / verdicts / reel
# --------------------------------------------------------------------------- #
def upsert_box(uid: str, pid: str, box: dict) -> None:
    _proj_ref(uid, pid).collection("boxes").document(box["id"]).set(box, merge=True)


def upsert_boxes(uid: str, pid: str, boxes: Iterable[dict]) -> None:
    batch = db().batch()
    col = _proj_ref(uid, pid).collection("boxes")
    for b in boxes:
        batch.set(col.document(b["id"]), b, merge=True)
    batch.commit()


def add_evidence(uid: str, pid: str, ev: dict, vector: list[float] | None = None) -> None:
    doc = dict(ev)
    if vector is not None:
        doc["vector768"] = firestore.DELETE_FIELD
    _proj_ref(uid, pid).collection("evidence").document(ev["id"]).set(doc, merge=True)
    if vector is not None:
        _proj_ref(uid, pid).collection("vectors").document(ev["id"]).set({"vector768": vector})


def add_evidence_batch(uid: str, pid: str, items: list[tuple[dict, list[float] | None]]) -> None:
    batch = db().batch()
    col = _proj_ref(uid, pid).collection("evidence")
    vec_col = _proj_ref(uid, pid).collection("vectors")
    for ev, vec in items:
        doc = dict(ev)
        if vec is not None:
            doc["vector768"] = firestore.DELETE_FIELD
        batch.set(col.document(ev["id"]), doc, merge=True)
        if vec is not None:
            batch.set(vec_col.document(ev["id"]), {"vector768": vec})
    batch.commit()


def list_evidence(uid: str, pid: str) -> list[dict]:
    ref = _proj_ref(uid, pid)
    vectors = {d.id: (d.to_dict() or {}).get("vector768") for d in ref.collection("vectors").stream()}
    rows = []
    for d in ref.collection("evidence").stream():
        row = d.to_dict() or {}
        row["id"] = row.get("id") or d.id
        if d.id in vectors:
            row["vector768"] = vectors[d.id]
        rows.append(row)
    return rows


_REPORT_EV_FIELDS = [
    "text", "url", "title", "source_domain", "publish_date", "modality",
    "objective_id", "license_note", "source", "source_tier", "quality_score",
    "image_url", "media_url", "round", "map_x", "map_y",
]


def list_evidence_report(uid: str, pid: str) -> list[dict]:
    """Evidence without the 768-float vectors — for the PDF report."""
    col = _proj_ref(uid, pid).collection("evidence")
    return [d.to_dict() for d in col.select(_REPORT_EV_FIELDS).stream()]


def list_boxes(uid: str, pid: str) -> list[dict]:
    return [d.to_dict() for d in _proj_ref(uid, pid).collection("boxes").stream()]


def list_runs(uid: str, pid: str) -> list[dict]:
    return [
        d.to_dict()
        for d in _proj_ref(uid, pid).collection("runs").order_by("run").stream()
    ]


def list_verdicts(uid: str, pid: str) -> list[dict]:
    return [d.to_dict() for d in _proj_ref(uid, pid).collection("verdicts").stream()]


def get_reel(uid: str, pid: str) -> list[dict]:
    snap = _proj_ref(uid, pid).collection("meta").document("reel").get()
    return (snap.to_dict() or {}).get("beats", []) if snap.exists else []


def add_run(uid: str, pid: str, record: dict) -> None:
    _proj_ref(uid, pid).collection("runs").document(str(record["run"])).set(record)


def add_verdict(uid: str, pid: str, v: dict) -> None:
    vid = f"{v['a_id']}_{v['b_id']}"
    _proj_ref(uid, pid).collection("verdicts").document(vid).set(v)


def set_reel(uid: str, pid: str, beats: list[dict]) -> None:
    _proj_ref(uid, pid).collection("meta").document("reel").set({"beats": beats})


def set_prior_art(uid: str, pid: str, data: dict) -> None:
    _proj_ref(uid, pid).collection("meta").document("prior_art").set(data)


def get_prior_art(uid: str, pid: str) -> dict | None:
    snap = _proj_ref(uid, pid).collection("meta").document("prior_art").get()
    return snap.to_dict() if snap.exists else None


# --------------------------------------------------------------------------- #
# files
# --------------------------------------------------------------------------- #
def put_file(uid: str, pid: str, name: str, data: bytes, content_type: str) -> str:
    path = f"users/{uid}/projects/{pid}/uploads/{name}"
    blob = bucket().blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return path


def save_source_snapshot(uid: str, pid: str, ev_id: str, text: str) -> str:
    path = f"users/{uid}/projects/{pid}/sources/{ev_id}.txt"
    bucket().blob(path).upload_from_string(text.encode("utf-8"), content_type="text/plain")
    return path
