"""Runtime configuration. Reads .env if present, then the process environment."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")  # set in .env
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
USE_VERTEX = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

# Vertex serves Gemini 3.x and Gemini Embedding 2 on the "global" location.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", USE_VERTEX)
if PROJECT:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)

BUCKET = os.environ.get("BOXES_BUCKET") or (f"{PROJECT}-boxes" if PROJECT else "")
EMBED_MODEL = os.environ.get("BOXES_EMBED_MODEL", "gemini-embedding-2")
CHAT_MODEL = os.environ.get("BOXES_CHAT_MODEL", "gemini-3.8-flash")
AGENT_SA = os.environ.get("BOXES_AGENT_SA", "")

PARALLEL_SEARCH_URL = os.environ.get("PARALLEL_SEARCH_URL", "https://api.parallel.ai/v1/search")


def parallel_api_key() -> str | None:
    """Key from the environment, else from Secret Manager secret PARALLEL_API_KEY."""
    key = os.environ.get("PARALLEL_API_KEY")
    if key:
        return key
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT}/secrets/PARALLEL_API_KEY/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode("utf-8").strip()
    except Exception:
        return None
