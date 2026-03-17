"""Codebase router — CRUD for codebases (no ingestion)."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser
from app.db.supabase import get_access_token, get_supabase_user
from app.schemas.codebase import (
    CodebaseCreate,
    CodebaseDetailResponse,
    CodebaseListResponse,
    CodebaseResponse,
    CodebaseUpdate,
)

router = APIRouter()


def _supabase_user(access_token: Annotated[str, Depends(get_access_token)]):
    return get_supabase_user(access_token)


@router.post("", response_model=CodebaseResponse)
async def create_codebase(
    body: CodebaseCreate,
    user: CurrentUser,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """Create a new codebase (name, optional description)."""
    data = {"name": body.name, "description": body.description}
    # RLS enforces user_id = auth.uid() on INSERT; we must pass user_id
    data["user_id"] = user["id"]

    r = supabase.table("codebase").insert(data).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to create codebase")
    return r.data[0]


@router.get("", response_model=CodebaseListResponse)
async def list_codebases(
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """List codebases accessible to the current user."""
    try:
        r = supabase.table("codebase").select("*").order("created_at", desc=True).execute()
        if getattr(r, "error", None):
            raise HTTPException(status_code=500, detail=str(r.error))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return CodebaseListResponse(codebases=r.data or [])


@router.get("/{id}", response_model=CodebaseDetailResponse)
async def get_codebase(
    id: UUID,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """Codebase detail and version history."""
    r = supabase.table("codebase").select("*").eq("id", str(id)).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="Codebase not found")
    codebase = r.data[0]

    vr = supabase.table("codebase_version").select("*").eq("codebase_id", str(id)).order("version", desc=True).execute()
    versions = vr.data or []

    return CodebaseDetailResponse(**codebase, versions=versions)


@router.patch("/{id}", response_model=CodebaseResponse)
async def update_codebase(
    id: UUID,
    body: CodebaseUpdate,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """Update codebase name and/or description."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    r = supabase.table("codebase").update(updates).eq("id", str(id)).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="Codebase not found")
    return r.data[0]


@router.delete("/{id}", status_code=204)
async def delete_codebase(
    id: UUID,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """Delete codebase and all its graph data (CASCADE)."""
    r = supabase.table("codebase").delete().eq("id", str(id)).execute()
    # RLS ensures we can only delete our own; no rows affected = not found or no permission
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="Codebase not found")
