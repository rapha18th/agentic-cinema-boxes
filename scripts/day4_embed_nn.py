"""Day 4 proof: embed a small multimodal batch with Gemini Embedding 2, add it
to the local vector store, and run a nearest-neighbor query.

Run: python scripts/day4_embed_nn.py
"""

from __future__ import annotations

import struct
import sys
import zlib

sys.path.insert(0, "src")

from google.genai import types  # noqa: E402

from boxes.embeddings import embed_parts, embed_texts, image_part, TASK_SEARCH  # noqa: E402
from boxes.vectorstore import VectorStore  # noqa: E402


def solid_png(r: int, g: int, b: int, w: int = 48, h: int = 48) -> bytes:
    raw = b"".join(b"\x00" + bytes([r, g, b]) * w for _ in range(h))

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


DOCS = [
    "Austrian hyperinflation of 1921 to 1922: the krone collapsed and prices reset daily.",
    "Interiors of Vienna banking halls in the 1920s: marble counters, brass grilles, frosted glass.",
    "Weimar-era street fashion: cloche hats, dropped waists, wool overcoats against the cold.",
    "Sound of a busy trading floor: overlapping voices, telephone bells, paper tearing.",
    "The Creditanstalt bank failure of 1931 and its run on deposits.",
]


def main() -> None:
    store = VectorStore(dim=768)

    doc_vecs = embed_texts(DOCS, dim=768)
    store.add(doc_vecs, [{"text": d, "kind": "text"} for d in DOCS])

    amber = solid_png(255, 180, 80)
    v_multi = embed_parts(
        [image_part(amber), types.Part(text="a warm gaslit bank hall")],
        dim=768,
    )
    store.add([v_multi], [{"text": "[image+caption] warm gaslit bank hall", "kind": "multimodal"}])

    print(f"index size: {len(store)}")

    for q in ["what did money feel like that year", "how did the banks look inside"]:
        qv = embed_texts([q], dim=768, prefix=TASK_SEARCH)[0]
        print(f"\nquery: {q}")
        for score, meta in store.search(qv, k=3):
            print(f"  {score:.3f}  {meta['kind']:10}  {meta['text'][:70]}")

    gaps = store.coverage_gaps(k=2, quantile=0.34)
    print("\ncoverage-gap row indices (sparsest edge):", gaps)


if __name__ == "__main__":
    main()
