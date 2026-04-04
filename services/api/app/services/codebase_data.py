from typing import List, Dict, Optional

from fastapi import HTTPException


def verify_codebase_access(supabase, codebase_id: str) -> None:
    """
    Verify the current user has access to the codebase via RLS.
    Raises HTTPException(404) if not found/accessible.
    """
    r = supabase.table("codebase").select("id").eq("id", codebase_id).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="Codebase not found")


def list_manifest_entries(
    supabase, codebase_id: str, limit: int = 1000, offset: int = 0
) -> List[Dict]:
    """
    Return manifest rows for a codebase ordered by file_path asc.
    Uses a defensive fetch strategy: request limit+offset rows then slice in-Python
    to support PostgREST servers that don't provide an `offset` operator.
    """
    q = (
        supabase.table("codebase_file_manifest")
        .select("*")
        .eq("codebase_id", codebase_id)
        .order("file_path", desc=False)
    )
    fetch_limit = min(limit + offset, 5000)
    r = q.limit(fetch_limit).execute()
    rows = r.data or []
    return rows[offset : offset + limit]


def list_codebase_versions(
    supabase, codebase_id: str, limit: int = 100, offset: int = 0
) -> List[Dict]:
    """
    Return version rows for a codebase ordered by version desc.
    """
    q = (
        supabase.table("codebase_version")
        .select("*")
        .eq("codebase_id", codebase_id)
        .order("version", desc=True)
    )
    fetch_limit = min(limit + offset, 500)
    r = q.limit(fetch_limit).execute()
    rows = r.data or []
    return rows[offset : offset + limit]


def get_current_codebase_version(supabase, codebase_id: str) -> Optional[Dict]:
    """
    Return the latest codebase_version row or None if no versions exist.
    """
    r = (
        supabase.table("codebase_version")
        .select("*")
        .eq("codebase_id", codebase_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not r.data or len(r.data) == 0:
        return None
    return r.data[0]

