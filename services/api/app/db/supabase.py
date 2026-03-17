"""
Supabase client helpers.
- User-scoped client (anon key + user JWT) for RLS-enforced codebase operations.
- Admin client (service role key) for admin user operations.
"""
import os
from typing import Annotated

from fastapi import Depends
from postgrest import SyncPostgrestClient
from supabase import create_client, Client

from app.auth.jwt import security, verify_jwt


def get_supabase_admin() -> Client:
    """Supabase client with service role key (bypasses RLS). For admin operations."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


async def get_access_token(
    credentials: Annotated[object, Depends(security)],
) -> str:
    """Extract and verify Bearer token; return raw token for Supabase client."""
    if not credentials:
        raise ValueError("Missing credentials")
    token = credentials.credentials
    verify_jwt(token)  # raises HTTPException if invalid
    return token


class _PostgrestTableProxy:
    """Thin wrapper so .table(name) returns a .from_(name) postgrest client for RLS."""

    def __init__(self, client: SyncPostgrestClient):
        self._client = client

    def table(self, name: str):
        return self._client.from_(name)


def get_supabase_user(access_token: str) -> _PostgrestTableProxy:
    """Postgrest client with anon key + user JWT for RLS-enforced requests.
    Uses postgrest directly to avoid supabase-py ClientOptions.storage incompatibility."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY required")
    rest_url = f"{url}/rest/v1"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    client = SyncPostgrestClient(rest_url, headers=headers)
    return _PostgrestTableProxy(client)
