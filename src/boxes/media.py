"""Trim harvested audio and video to a short clip before embedding.

Archival recordings run long, and Gemini Embedding 2 rejects a large payload.
It only needs a representative slice, and the full asset stays linked at its
source. ffmpeg does the real work when present; without it, a container-aware
byte truncation handles the common Ogg and MP3 cases so a local snapshot run
still produces audio.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

HAS_FFMPEG = shutil.which("ffmpeg") is not None

# Well under Gemini Embedding 2's inline-payload ceiling for the fallback path.
_BYTE_TRIM_TARGET = 1_400_000

_EXT = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/flac": ".flac", "audio/ogg": ".ogg",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
}


def _trim_ogg(data: bytes, target: int) -> bytes | None:
    """Keep whole Ogg pages up to ~target bytes. Pages start with 'OggS'; a
    stream that simply ends early still decodes."""
    if data[:4] != b"OggS":
        return None
    end = data.find(b"OggS", 4)
    while 0 < end <= target:
        nxt = data.find(b"OggS", end + 4)
        if nxt == -1:
            break
        end = nxt
    return data[:end] if end > 4 else None


def _trim_mp3(data: bytes, target: int) -> bytes | None:
    """Drop an ID3v2 tag, keep bytes up to ~target, then cut back to a frame
    sync so the last frame is whole."""
    start = 0
    if data[:3] == b"ID3" and len(data) > 10:
        size = 0
        for b in data[6:10]:
            size = (size << 7) | (b & 0x7F)  # syncsafe integer
        start = 10 + size
    if start >= len(data):
        return None
    cut = min(len(data), start + target)
    for i in range(cut, max(start, cut - 4000), -1):
        if data[i - 1] == 0xFF and (data[i] & 0xE0) == 0xE0:
            return data[start:i - 1]
    return data[start:cut]


def _byte_trim(data: bytes, mime: str) -> tuple[bytes, str, bool]:
    if len(data) <= _BYTE_TRIM_TARGET:
        return data, mime, False
    try:
        if data[:4] == b"OggS":
            out = _trim_ogg(data, _BYTE_TRIM_TARGET)
            if out:
                return out, mime, True
        if mime in ("audio/mpeg", "audio/mp3") or data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
            out = _trim_mp3(data, _BYTE_TRIM_TARGET)
            if out:
                return out, "audio/mpeg", True
    except Exception:  # noqa: BLE001
        pass
    return data, mime, False


def trim_av(data: bytes, mime: str, *, seconds: int = 20) -> tuple[bytes, str, bool]:
    """Return (bytes, mime, trimmed). On any failure, the original is returned."""
    if not data:
        return data, mime, False
    if not HAS_FFMPEG:
        return _byte_trim(data, mime)
    kind = "video" if mime.startswith("video/") else "audio"
    in_ext = _EXT.get(mime, ".bin")
    out_ext = ".mp4" if kind == "video" else ".mp3"
    out_mime = "video/mp4" if kind == "video" else "audio/mpeg"
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"in{in_ext}"
        dst = Path(td) / f"out{out_ext}"
        src.write_bytes(data)
        cmd = ["ffmpeg", "-y", "-i", str(src), "-t", str(seconds)]
        if kind == "video":
            cmd += ["-vf", "scale='min(640,iw)':-2", "-an", "-r", "12",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "30"]
        else:
            cmd += ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k"]
        cmd.append(str(dst))
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
            out = dst.read_bytes()
        except (subprocess.SubprocessError, OSError):
            return _byte_trim(data, mime)
    if not out or len(out) > 12_000_000:
        return _byte_trim(data, mime)
    return out, out_mime, True
