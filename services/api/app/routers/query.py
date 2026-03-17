"""Query router — natural-language search (stub)."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser
from app.db.supabase import get_access_token, get_supabase_user
from app.schemas.query import QueryRequest, QueryStubResponse

router = APIRouter()


def _supabase_user(access_token: Annotated[str, Depends(get_access_token)]):
    return get_supabase_user(access_token)


async def _verify_codebase_access(
    codebase_id: UUID,
    supabase,
) -> None:
    """Verify codebase exists and user has access (RLS). Raises 404 if not."""
    r = supabase.table("codebase").select("id").eq("id", str(codebase_id)).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="Codebase not found")


@router.post("/{id}/query", response_model=QueryStubResponse)
async def run_query(
    id: UUID,
    body: QueryRequest,
    user: CurrentUser,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """
    Run natural-language query (scoped to codebase).
    Implementation pending — returns stub response.
    """
    await _verify_codebase_access(id, supabase)

    return QueryStubResponse(
        status="pending",
        message="Implementation pending",
        query=body.query,
        explain=body.explain,
    )
