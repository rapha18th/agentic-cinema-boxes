"""Verify Firebase ID tokens. The uid from the token is the only thing that
decides which subtree a request can touch.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth

_ALLOW_DEV = os.environ.get("BOXES_DEV_UID")  # local testing only


async def current_uid(authorization: str | None = Header(default=None)) -> str:
    if _ALLOW_DEV and not authorization:
        return _ALLOW_DEV
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"invalid token: {e}") from e
    return decoded["uid"]
