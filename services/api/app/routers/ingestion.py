"""Ingestion router — file upload, job creation, SSE stream."""
import asyncio
import json
import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.auth.dependencies import CurrentUser
from app.db.supabase import get_access_token, get_supabase_user, get_supabase_admin
from app.queue.redis import enqueue_ingestion_job, get_job_status
from app.schemas.ingestion import IngestionJobResponse
from app.schemas.codebase import (
    CodebaseManifestResponse,
    CodebaseVersionsResponse,
    CodebaseCurrentVersionResponse,
)
from app.services.codebase_data import (
    list_manifest_entries,
    list_codebase_versions,
    get_current_codebase_version,
)

logger = logging.getLogger(__name__)

ZIPS_BUCKET = "codegraph-zips"
router = APIRouter()


def _supabase_user(access_token: Annotated[str, Depends(get_access_token)]):
    return get_supabase_user(access_token)


async def _verify_codebase_access(
    codebase_id: UUID,
    supabase,
) -> None:
    """Verify codebase exists and user has access (RLS). Raises 404 if not."""
    logger.info("verify_codebase_access started codebase_id=%s", codebase_id)
    r = supabase.table("codebase").select("id").eq("id", str(codebase_id)).execute()
    if not r.data or len(r.data) == 0:
        logger.warning("verify_codebase_access ended codebase_id=%s access=denied", codebase_id)
        raise HTTPException(status_code=404, detail="Codebase not found")
    logger.info("verify_codebase_access ended codebase_id=%s access=ok", codebase_id)


@router.post("/{id}/ingest", response_model=IngestionJobResponse)
async def create_ingestion_job(
    id: UUID,
    user: CurrentUser,
    supabase: Annotated[object, Depends(_supabase_user)],
    file: UploadFile = File(...),
):
    """
    Accept file upload, persist ZIP to Storage, enqueue ingestion job, return job_id.
    """
    logger.info(
        "create_ingestion_job started codebase_id=%s user_id=%s filename=%s",
        id, user["id"], file.filename,
    )

    await _verify_codebase_access(id, supabase)

    job_id = str(uuid4())
    zip_storage_key = f"codebases/{id}/{job_id}.zip"

    content = await file.read()
    logger.info("create_ingestion_job file read filename=%s size=%s", file.filename, len(content))

    admin_supabase = get_supabase_admin()
    admin_supabase.storage.from_(ZIPS_BUCKET).upload(
        path=zip_storage_key,
        file=content,
        file_options={"content-type": "application/zip", "upsert": "true"},
    )
    logger.info("create_ingestion_job uploaded to storage key=%s", zip_storage_key)

    job_id = await enqueue_ingestion_job(
        codebase_id=str(id),
        user_id=user["id"],
        zip_storage_key=zip_storage_key,
        job_id=job_id,
    )
    logger.info("create_ingestion_job enqueued job_id=%s", job_id)

    logger.info("create_ingestion_job ended codebase_id=%s job_id=%s", id, job_id)
    return IngestionJobResponse(
        job_id=job_id,
        status="queued",
        message="Job queued for processing",
    )


@router.get("/{id}/ingest/jobs/{job_id}/stream")
async def stream_ingestion_job(
    id: UUID,
    job_id: str,
    user: CurrentUser,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """
    SSE stream for ingestion job status updates.
    Stub: streams one event then closes.
    """
    logger.info(
        "stream_ingestion_job started codebase_id=%s job_id=%s user_id=%s",
        id, job_id, user["id"],
    )

    await _verify_codebase_access(id, supabase)

    logger.info("stream_ingestion_job fetching job status job_id=%s", job_id)
    job = await get_job_status(job_id)
    if not job:
        logger.warning("stream_ingestion_job job not found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("stream_ingestion_job job status fetched job_id=%s", job_id)

    if job.get("codebase_id") != str(id) or job.get("user_id") != user["id"]:
        logger.warning("stream_ingestion_job access denied job_id=%s", job_id)
        raise HTTPException(status_code=403, detail="Access denied")
    logger.info("stream_ingestion_job ownership verified job_id=%s", job_id)

    async def event_generator():
        logger.info("stream_ingestion_job streaming started job_id=%s", job_id)
        terminal_states = {"completed", "failed"}
        while True:
            job = await get_job_status(job_id)
            if not job:
                break
            status = job.get("status", "unknown")
            message = job.get("message", "")
            data = {"status": status, "message": message}
            yield f"data: {json.dumps(data)}\n\n"
            if status in terminal_states:
                break
            await asyncio.sleep(1)
        logger.info("stream_ingestion_job streaming ended job_id=%s", job_id)

    logger.info("stream_ingestion_job ended job_id=%s returning SSE response", job_id)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{id}/manifest", response_model=CodebaseManifestResponse)
async def get_manifest(
    id: UUID,
    supabase: Annotated[object, Depends(_supabase_user)],
    limit: int = 1000,
    offset: int = 0,
):
    """
    List indexed files + hashes for this codebase.
    Query params: limit (default 1000, max 5000), offset (default 0).
    """
    await _verify_codebase_access(id, supabase)
    # Defensive fetch implemented in service (fetch limit+offset then slice)
    entries = list_manifest_entries(supabase, str(id), limit=limit, offset=offset)
    return CodebaseManifestResponse(entries=entries)


@router.get("/{id}/versions", response_model=CodebaseVersionsResponse)
async def get_versions(
    id: UUID,
    supabase: Annotated[object, Depends(_supabase_user)],
    limit: int = 100,
    offset: int = 0,
):
    """
    Return ingestion version history for a codebase, ordered by version desc.
    """
    await _verify_codebase_access(id, supabase)
    versions = list_codebase_versions(supabase, str(id), limit=limit, offset=offset)
    return CodebaseVersionsResponse(versions=versions)


@router.get("/{id}/versions/current", response_model=CodebaseCurrentVersionResponse)
async def get_current_version(
    id: UUID,
    supabase: Annotated[object, Depends(_supabase_user)],
):
    """
    Return the current (latest) codebase version or null if none exist.
    """
    await _verify_codebase_access(id, supabase)
    current = get_current_codebase_version(supabase, str(id))
    return CodebaseCurrentVersionResponse(current_version=current)
