"""Unit tests for the Supabase JWT auth dependency (HS256 path via test secret)."""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.auth import User, get_current_user

SECRET = "test-jwt-secret-0123456789abcdef0123456789abcdef"


def make_token(**overrides) -> str:
    payload = {
        "sub": "user-123",
        "email": "writer@example.org",
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
    }
    payload.update(overrides)
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


async def test_valid_token_returns_user():
    user = await get_current_user(f"Bearer {make_token()}")
    assert isinstance(user, User)
    assert user.id == "user-123"
    assert user.email == "writer@example.org"


async def test_missing_header_rejected():
    with pytest.raises(HTTPException) as exc:
        await get_current_user("")
    assert exc.value.status_code == 401


async def test_non_bearer_scheme_rejected():
    with pytest.raises(HTTPException):
        await get_current_user("Basic abc")


async def test_expired_token_rejected():
    expired = make_token(exp=int(time.time()) - 100)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(f"Bearer {expired}")
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


async def test_garbage_token_rejected():
    with pytest.raises(HTTPException) as exc:
        await get_current_user("Bearer not-a-jwt")
    assert exc.value.status_code == 401


async def test_wrong_signature_rejected():
    with pytest.raises(HTTPException):
        await get_current_user(
            f"Bearer {pyjwt.encode({'sub': 'x', 'aud': 'authenticated', 'exp': int(time.time()) + 100}, 'wrong-secret', algorithm='HS256')}"
        )


async def test_missing_sub_rejected():
    token = pyjwt.encode(
        {"aud": "authenticated", "exp": int(time.time()) + 100}, SECRET, algorithm="HS256"
    )
    with pytest.raises(HTTPException):
        await get_current_user(f"Bearer {token}")
