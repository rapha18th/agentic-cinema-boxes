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


def get_project(uid: str, pid: str) -> dict | None:
    snap = _proj_ref(uid, pid).get()
    return snap.to_dict() if snap.exists else None


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
        doc["vector768"] = vector
    _proj_ref(uid, pid).collection("evidence").document(ev["id"]).set(doc, merge=True)


def add_evidence_batch(uid: str, pid: str, items: list[tuple[dict, list[float] | None]]) -> None:
    batch = db().batch()
    col = _proj_ref(uid, pid).collection("evidence")
    for ev, vec in items:
        doc = dict(ev)
        if vec is not None:
            doc["vector768"] = vec
        batch.set(col.document(ev["id"]), doc, merge=True)
    batch.commit()


def list_evidence(uid: str, pid: str) -> list[dict]:
    return [d.to_dict() for d in _proj_ref(uid, pid).collection("evidence").stream()]


def add_run(uid: str, pid: str, record: dict) -> None:
    _proj_ref(uid, pid).collection("runs").document(str(record["run"])).set(record)


def add_verdict(uid: str, pid: str, v: dict) -> None:
    vid = f"{v['a_id']}_{v['b_id']}"
    _proj_ref(uid, pid).collection("verdicts").document(vid).set(v)


def set_reel(uid: str, pid: str, beats: list[dict]) -> None:
    _proj_ref(uid, pid).collection("meta").document("reel").set({"beats": beats})


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
