"""
Ingestion worker — consumes Redis jobs, runs two-phase pipeline.
All DB changes happen only at the end. On any prep failure: cancel, do not modify DB.
"""
import asyncio
import io
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import redis.asyncio as redis

from .storage_uploader import (
    ZIPS_BUCKET,
    _get_supabase,
    get_next_version,
    insert_codebase_version,
    upload_file,
    upsert_manifest,
)
from .scanner import scan_directory
from .hasher import compute_file_hash
from .lsp.client import LspClient
from .lsp.servers.java import start_jdtls, get_initialization_options
from .crawl.phase1 import crawl_phase1
from .graph_writer import GraphWriter

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "ingestion:queue"
INGESTION_JOB_PREFIX = "ingestion:job:"
BLPOP_TIMEOUT = 30


def _get_redis():
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(url, decode_responses=True)


async def dequeue_job(timeout_sec: int = BLPOP_TIMEOUT) -> dict | None:
    """Block until a job is available or timeout. Returns job payload or None."""
    logger.info("dequeue_job started timeout_sec=%s", timeout_sec)
    client = _get_redis()
    try:
        result = await client.blpop(INGESTION_QUEUE_KEY, timeout=timeout_sec)
    finally:
        await client.aclose()

    if result is None:
        logger.info("dequeue_job ended timeout no job")
        return None

    _, job_id = result
    job_key = f"{INGESTION_JOB_PREFIX}{job_id}"
    client = _get_redis()
    try:
        payload = await client.hgetall(job_key)
    finally:
        await client.aclose()

    logger.info("dequeue_job ended job_id=%s found=%s", job_id, payload is not None)
    return payload if payload else None


async def update_job_status(job_id: str, status: str, message: str | None = None) -> None:
    """Update job status in Redis."""
    logger.info("update_job_status started job_id=%s status=%s", job_id, status)
    client = _get_redis()
    try:
        job_key = f"{INGESTION_JOB_PREFIX}{job_id}"
        await client.hset(job_key, "status", status)
        if message is not None:
            await client.hset(job_key, "message", message)
    finally:
        await client.aclose()
    logger.info("update_job_status ended job_id=%s status=%s", job_id, status)


async def process_job(payload: dict) -> None:
    """
    Process a single ingestion job.
    Two-phase: preparation (no DB) then commit (Storage, manifest, version).
    On any prep failure: set failed, do not touch DB.
    """
    job_id = payload.get("job_id")
    codebase_id = payload.get("codebase_id")
    user_id = payload.get("user_id")
    zip_storage_key = payload.get("zip_storage_key")

    logger.info("process_job started job_id=%s codebase_id=%s", job_id, codebase_id)

    if not zip_storage_key:
        logger.error("process_job missing zip_storage_key job_id=%s", job_id)
        await update_job_status(job_id, "failed", "Missing zip_storage_key")
        logger.info("process_job ended job_id=%s status=failed", job_id)
        return

    try:
        await update_job_status(job_id, "processing")

        # --- Preparation phase (no DB writes — any failure cancels) ---
        extract_path, batch = _download_extract_scan_hash(
            job_id, codebase_id, zip_storage_key
        )

        # Validate batch before commit
        if not batch:
            logger.warning("process_job empty batch job_id=%s", job_id)
            # Empty is OK — maybe ZIP had no eligible files
            batch = []
        
        # --- Phase 1: LSP analysis for Java files ---
        # Determine workspace root (extracted ZIP root)
        tmpdir = Path(extract_path)
        top_level = list(tmpdir.iterdir())
        if len(top_level) == 1 and top_level[0].is_dir():
            workspace_root = str(top_level[0])
        else:
            workspace_root = str(tmpdir)
        
        java_files = [
            str((Path(workspace_root) / rel_path).resolve())
            for rel_path, _, _ in batch
            if rel_path.endswith(".java")
        ]
        
        if java_files:
            logger.info("process_job: found %d Java files, running Phase 1", len(java_files))
            try:
                nodes, contains_edges = _run_phase1_java(
                    workspace_root,
                    java_files,
                    codebase_id,
                )
                
                # Write to Neo4j
                logger.info("process_job: writing %d nodes to Neo4j", len(nodes))
                graph_writer = GraphWriter()
                try:
                    graph_writer.write_phase1(nodes, contains_edges, codebase_id)
                    # Verify graph written: query counts for this codebase
                    stats = graph_writer.get_graph_stats_for_codebase(codebase_id)
                    logger.info(
                        "process_job: graph stats for codebase_id=%s: nodes=%d relationships=%d",
                        codebase_id,
                        stats["node_count"],
                        stats["relationship_count"],
                    )
                finally:
                    graph_writer.close()
                
                logger.info("process_job: Phase 1 completed successfully")
            except Exception as e:
                logger.exception("process_job: Phase 1 failed: %s", e)
                raise  # Cancel job on Phase 1 failure
        else:
            logger.info("process_job: no Java files found, skipping Phase 1")

        # --- Commit phase (only after preparation succeeds — order matters) ---
        supabase = _get_supabase()

        # 1. Storage — upload all files to codegraph-sources
        logger.info("process_job commit phase: uploading to Storage job_id=%s", job_id)
        manifest_entries = []
        for rel_path, content_hash, content_bytes in batch:
            storage_ref = upload_file(supabase, codebase_id, rel_path, content_bytes)
            manifest_entries.append((rel_path, content_hash, storage_ref))

        # 2. codebase_file_manifest — upsert all rows
        logger.info("process_job commit phase: upsert manifest job_id=%s", job_id)
        upsert_manifest(supabase, codebase_id, manifest_entries)

        # 3. codebase_version — insert new version row
        logger.info("process_job commit phase: insert codebase_version job_id=%s", job_id)
        next_ver = get_next_version(supabase, codebase_id)
        insert_codebase_version(
            supabase,
            codebase_id,
            version=next_ver,
            files_added=len(manifest_entries),
            files_modified=0,
            files_deleted=0,
            files_unchanged=0,
        )

        # 4. Update job status
        await update_job_status(job_id, "completed", f"Indexed {len(manifest_entries)} files")

        if extract_path and Path(extract_path).exists():
            shutil.rmtree(extract_path, ignore_errors=True)

    except Exception as e:
        logger.exception("process_job failed job_id=%s error=%s", job_id, e)
        await update_job_status(job_id, "failed", str(e))

    logger.info("process_job ended job_id=%s", job_id)


def _run_phase1_java(
    workspace_root: str,
    java_files: list[str],
    codebase_id: str,
) -> tuple[list[dict], list[dict]]:
    """
    Run Phase 1 crawl for Java files using jdtls.
    
    Args:
        workspace_root: Root directory of the workspace
        java_files: List of absolute paths to Java files
        codebase_id: Codebase UUID
        
    Returns:
        (nodes, contains_edges) tuple
    """
    logger.info("_run_phase1_java started: files=%d", len(java_files))
    
    # Start jdtls
    process = start_jdtls(workspace_root)
    client = None
    
    try:
        # Initialize LSP client
        client = LspClient(process, workspace_root)
        init_options = get_initialization_options(workspace_root)
        client.initialize(init_options)
        
        # Run Phase 1 crawl
        nodes, contains_edges = crawl_phase1(
            client,
            java_files,
            "java",
            codebase_id,
        )
        
        logger.info(
            "_run_phase1_java completed: nodes=%d contains_edges=%d",
            len(nodes),
            len(contains_edges),
        )
        
        return nodes, contains_edges
        
    except Exception as e:
        logger.exception("_run_phase1_java failed: %s", e)
        raise
    finally:
        if client:
            client.close()
        logger.info("_run_phase1_java: LSP client closed")


def _download_extract_scan_hash(
    job_id: str,
    codebase_id: str,
    zip_storage_key: str,
) -> tuple[str | None, list[tuple[str, str, bytes]]]:
    """
    Preparation phase: download ZIP, extract, scan, hash.
    Returns (extract_path, batch) where batch is [(rel_path, content_hash, content_bytes), ...].
    """
    logger.info(
        "download_and_extract_scan_hash started job_id=%s zip_storage_key=%s",
        job_id, zip_storage_key,
    )

    supabase = _get_supabase()

    # Download ZIP from Storage
    zip_bytes = supabase.storage.from_(ZIPS_BUCKET).download(zip_storage_key)
    logger.info("download_and_extract_scan_hash downloaded bytes=%s", len(zip_bytes))

    # Extract to temp dir
    tmpdir = tempfile.mkdtemp(prefix=f"ingest-{job_id}-")
    root = Path(tmpdir)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        zf.extractall(root)
    logger.info("download_and_extract_scan_hash extracted to %s", tmpdir)

    # Find root of extracted content (ZIP may have a top-level folder or not)
    top_level = list(root.iterdir())
    if len(top_level) == 1 and top_level[0].is_dir():
        scan_root = top_level[0]
    else:
        scan_root = root

    # Scan for eligible files
    eligible_paths = scan_directory(scan_root)

    # Hash and read each file — do not upload yet
    batch = []
    for path in eligible_paths:
        try:
            rel_path = str(path.relative_to(scan_root)).replace("\\", "/")
            content_hash = compute_file_hash(path)
            content_bytes = path.read_bytes()
            batch.append((rel_path, content_hash, content_bytes))
        except Exception as e:
            logger.warning("download_and_extract_scan_hash file error path=%s e=%s", path, e)
            raise  # Cancel job on any file error

    logger.info(
        "download_and_extract_scan_hash ended job_id=%s batch_size=%s",
        job_id, len(batch),
    )
    return tmpdir, batch
