"""A small local vector store: brute-force nearest neighbor over an in-memory
matrix, with save and load to an .npz file.

Enough for hackathon-scale corpora and for the demo. Swap the query method for
Vertex AI Vector Search when the corpus outgrows memory. The interface stays the
same: add(), search(), save(), load().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class VectorStore:
    dim: int = 768
    _vecs: np.ndarray | None = field(default=None, repr=False)
    _meta: list[dict] = field(default_factory=list)

    def add(self, vectors: list[list[float]], metas: list[dict]) -> None:
        assert len(vectors) == len(metas)
        arr = np.asarray(vectors, dtype=np.float32)
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        self._vecs = arr if self._vecs is None else np.vstack([self._vecs, arr])
        self._meta.extend(metas)

    def __len__(self) -> int:
        return 0 if self._vecs is None else self._vecs.shape[0]

    def search(self, query_vec: list[float], k: int = 8) -> list[tuple[float, dict]]:
        if self._vecs is None:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sims = self._vecs @ q
        idx = np.argsort(-sims)[:k]
        return [(float(sims[i]), self._meta[i]) for i in idx]

    def coverage_gaps(self, k: int = 3, quantile: float = 0.15) -> list[int]:
        """Rows whose mean distance to their k nearest neighbors is in the
        sparsest quantile. Those points sit at the edge of the covered space,
        which is where the loop should search next."""
        if self._vecs is None or len(self) <= k + 1:
            return []
        sims = self._vecs @ self._vecs.T
        np.fill_diagonal(sims, -1.0)
        knn = np.sort(-np.sort(-sims, axis=1)[:, :k], axis=1)
        sparsity = 1.0 - knn.mean(axis=1)
        cutoff = np.quantile(sparsity, 1.0 - quantile)
        return [int(i) for i in np.where(sparsity >= cutoff)[0]]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        np.savez_compressed(path, vecs=self._vecs if self._vecs is not None else np.zeros((0, self.dim), np.float32))
        path.with_suffix(".meta.json").write_text(json.dumps(self._meta, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        path = Path(path)
        data = np.load(path)
        vs = cls(dim=int(data["vecs"].shape[1]) if data["vecs"].size else 768)
        vs._vecs = data["vecs"] if data["vecs"].size else None
        mp = path.with_suffix(".meta.json")
        vs._meta = json.loads(mp.read_text()) if mp.exists() else []
        return vs
