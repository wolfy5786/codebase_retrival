"""
FastAPI dependencies for authentication and authorization.
"""
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import get_user_from_payload, security, verify_jwt


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
) -> dict:
    """
    Validate JWT and return current user (id, email, app_metadata).
    Raises 401 if missing or invalid token.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    payload = verify_jwt(credentials.credentials)
    return get_user_from_payload(payload)


async def require_admin(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Require admin role. Raises 403 if user is not admin.
    Returns the current user dict.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Type aliases for cleaner router signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]
AdminUser = Annotated[dict, Depends(require_admin)]
