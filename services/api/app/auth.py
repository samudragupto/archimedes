"""Supabase JWT authentication for the FastAPI dependency layer.

The browser sends the user's Supabase access token as
``Authorization: Bearer <token>``. We verify it and trust only the ``sub``
claim (the auth.users id) — every DB query the routers make is additionally
filtered by that id, because the API uses the service-role client, which
bypasses RLS by design.

Two verification strategies (Supabase changed token signing in 2024+):
  * ``SUPABASE_JWT_SECRET`` set  → legacy HS256 shared-secret verification.
  * secret empty (default)       → fetch the project's JWKS from
    ``<SUPABASE_URL>/auth/v1/.well-known/jwks.json`` and verify ES256/RS256.
Both enforce audience "authenticated" with 30s clock-skew leeway.
"""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Header, HTTPException, status
from jwt.types import Options

from .config import get_settings

logger = logging.getLogger(__name__)


class User:
    """The only identity data routers may rely on."""

    __slots__ = ("id", "email")

    def __init__(self, id: str, email: str | None = None) -> None:
        self.id = id
        self.email = email

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!r})"


_jwks_client: jwt.PyJWKClient | None = None
_jwks_url: str | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client, _jwks_url
    settings = get_settings()
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if _jwks_client is None or _jwks_url != url:
        # PyJWKClient caches keys internally (with refresh on unknown kid).
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
        _jwks_url = url
    return _jwks_client


def _decode(token: str) -> dict:
    settings = get_settings()
    options: Options = {"require": ["exp", "sub"], "verify_aud": True}
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            leeway=30,
            options=options,
        )
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured: set SUPABASE_JWT_SECRET or SUPABASE_URL",
        )
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
        leeway=30,
        options=options,
    )


async def get_current_user(
    authorization: Annotated[str, Header()] = "",
) -> User:
    """FastAPI dependency: verify the Bearer token, return the user identity."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = _decode(token.strip())
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError as e:
        logger.info("JWT rejected: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token") from None
    except Exception as e:  # JWKS fetch/network problems → 503, not 500
        logger.warning("JWKS lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Auth backend unavailable") from None
    return User(id=str(payload["sub"]), email=payload.get("email"))
