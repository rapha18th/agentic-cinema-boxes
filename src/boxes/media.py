"""Trim harvested audio and video to a short clip before embedding.

Archival recordings run long. Gemini Embedding 2 only needs a representative
slice, and the full asset stays linked at its source. Uses ffmpeg when present;
falls back to the untouched bytes otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

HAS_FFMPEG = shutil.which("ffmpeg") is not None

_EXT = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/flac": ".flac", "audio/ogg": ".ogg",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
}


def trim_av(data: bytes, mime: str, *, seconds: int = 20) -> tuple[bytes, str, bool]:
    """Return (bytes, mime, trimmed). On any failure, the original is returned."""
    if not HAS_FFMPEG or not data:
        return data, mime, False
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
            return data, mime, False
    if not out or len(out) > 12_000_000:
        return data, mime, False
    return out, out_mime, True
