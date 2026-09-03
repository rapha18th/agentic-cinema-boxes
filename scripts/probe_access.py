"""Access check. Confirms this project can reach the models THE BOXES needs.

Run: python scripts/probe_access.py
"""

from __future__ import annotations

import sys
import struct
import zlib

sys.path.insert(0, "src")

from boxes import config  # noqa: E402
from boxes.embeddings import client, cosine  # noqa: E402
from google.genai import types  # noqa: E402


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


def main() -> int:
    print(f"project={config.PROJECT} location={config.LOCATION}")
    c = client()
    ok = True

    try:
        r = c.models.generate_content(model=config.CHAT_MODEL, contents="Reply with: BOXES OK")
        print(f"chat  {config.CHAT_MODEL}: {r.text!r}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"chat  {config.CHAT_MODEL}: ERROR {e}")

    try:
        r = c.models.embed_content(
            model=config.EMBED_MODEL,
            contents="warm candlelit amber interior, 1975 film look",
            config=types.EmbedContentConfig(output_dimensionality=3072),
        )
        print(f"embed {config.EMBED_MODEL}: text dim {len(r.embeddings[0].values)}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"embed {config.EMBED_MODEL}: ERROR {e}")

    try:
        amber = solid_png(255, 180, 80)
        vi = c.models.embed_content(
            model=config.EMBED_MODEL,
            contents=[types.Part.from_bytes(data=amber, mime_type="image/png")],
            config=types.EmbedContentConfig(output_dimensionality=3072),
        ).embeddings[0].values
        vw = c.models.embed_content(model=config.EMBED_MODEL, contents="warm amber candlelight").embeddings[0].values
        vc = c.models.embed_content(model=config.EMBED_MODEL, contents="cold blue fluorescent office").embeddings[0].values
        print(f"multimodal: amber image vs warm text {cosine(vi, vw):.3f}, vs cold text {cosine(vi, vc):.3f}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"multimodal: ERROR {e}")

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
