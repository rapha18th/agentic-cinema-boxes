"""Thin wrapper over Gemini for the reasoning steps: research planning, evidence
evaluation, contradiction verification, gap hypotheses, reel structuring.

One shared client. JSON in, parsed JSON out.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types

from . import config
from .embeddings import client, with_retry

# Planning, evaluation, and verification are structured, mechanical steps. Turn
# extended thinking off so each call is a few seconds, not twenty.
_NO_THINK = types.ThinkingConfig(thinking_budget=0)
_JSON_CFG = types.GenerateContentConfig(
    response_mime_type="application/json", temperature=0.2, thinking_config=_NO_THINK
)
_TEXT_CFG = types.GenerateContentConfig(temperature=0.3, thinking_config=_NO_THINK)


def generate(prompt: str, *, model: str | None = None) -> str:
    r = with_retry(lambda: client().models.generate_content(
        model=model or config.CHAT_MODEL, contents=prompt, config=_TEXT_CFG
    ))
    return (r.text or "").strip()


def generate_json(prompt: str, *, model: str | None = None) -> Any:
    """Ask for JSON and parse it. Falls back to a lenient extraction if the model
    wraps the payload in prose or a code fence."""
    r = with_retry(lambda: client().models.generate_content(
        model=model or config.CHAT_MODEL, contents=prompt, config=_JSON_CFG
    ))
    txt = (r.text or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    t = txt.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(t)
    except Exception:
        start = min((t.find(c) for c in "[{" if t.find(c) >= 0), default=-1)
        end = max(t.rfind("]"), t.rfind("}"))
        if start >= 0 and end > start:
            return json.loads(t[start : end + 1])
        raise
