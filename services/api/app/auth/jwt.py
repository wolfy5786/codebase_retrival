"""
Supabase JWT verification.
Validates Bearer tokens using JWKS (asymmetric keys) or legacy JWT secret (HS256).
"""
import os
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


def _get_jwks_uri() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")
    return f"{url}/auth/v1/.well-known/jwks.json"


def verify_jwt(token: str) -> dict[str, Any]:
    """
    Verify a Supabase JWT and return the decoded payload.
    Tries JWKS (ES256/RS256) first for projects using asymmetric signing keys,
    then falls back to legacy JWT secret (HS256).
    Raises HTTPException 401 if invalid.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    alg = header.get("alg", "HS256")
    if alg in ("ES256", "RS256", "EdDSA"):
        jwks_uri = _get_jwks_uri()
        jwks_client = PyJWKClient(jwks_uri)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        try:
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_user_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Extract user info from JWT payload.
    Returns dict with id, email, app_metadata.
    """
    sub = payload.get("sub")
    email = payload.get("email") or payload.get("sub")
    app_metadata = payload.get("app_metadata") or {}
    role = app_metadata.get("role", "user")
    return {
        "id": sub,
        "email": email,
        "app_metadata": {"role": role},
        "role": role,
    }
