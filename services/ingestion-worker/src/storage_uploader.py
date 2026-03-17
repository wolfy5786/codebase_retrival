"""
Supabase Storage upload and DB writes (manifest, codebase_version).
All writes happen in commit phase only. Use admin client (service role).
"""
import logging
import os
from supabase import create_client

logger = logging.getLogger(__name__)

SOURCES_BUCKET = "codegraph-sources"
ZIPS_BUCKET = "codegraph-zips"


def _get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def upload_file(
    supabase,
    codebase_id: str,
    file_path: str,
    content_bytes: bytes,
) -> str:
    """
    Upload file to codegraph-sources bucket.
    Returns storage_ref (object key).
    """
    storage_ref = f"codebases/{codebase_id}/files/{file_path}"
    logger.info("upload_file started storage_ref=%s file_path=%s", storage_ref, file_path)

    supabase.storage.from_(SOURCES_BUCKET).upload(
        path=storage_ref,
        file=content_bytes,
        file_options={"content-type": "text/plain; charset=utf-8", "upsert": "true"},
    )

    logger.info("upload_file ended storage_ref=%s", storage_ref)
    return storage_ref


def upsert_manifest(
    supabase,
    codebase_id: str,
    entries: list[tuple[str, str, str]],
) -> None:
    """
    Upsert codebase_file_manifest rows.
    entries: list of (file_path, content_hash, storage_ref)
    """
    logger.info("upsert_manifest started codebase_id=%s count=%s", codebase_id, len(entries))

    rows = [
        {
            "codebase_id": codebase_id,
            "file_path": file_path,
            "content_hash": content_hash,
            "storage_ref": storage_ref,
        }
        for file_path, content_hash, storage_ref in entries
    ]
    supabase.table("codebase_file_manifest").upsert(
        rows,
        on_conflict="codebase_id,file_path",
    ).execute()

    logger.info("upsert_manifest ended codebase_id=%s", codebase_id)


def insert_codebase_version(
    supabase,
    codebase_id: str,
    version: int,
    files_added: int,
    files_modified: int = 0,
    files_deleted: int = 0,
    files_unchanged: int = 0,
) -> None:
    """
    Insert new codebase_version row.
    """
    logger.info(
        "insert_codebase_version started codebase_id=%s version=%s",
        codebase_id, version,
    )

    supabase.table("codebase_version").insert(
        {
            "codebase_id": codebase_id,
            "version": version,
            "upload_source": "zip",
            "files_added": files_added,
            "files_modified": files_modified,
            "files_deleted": files_deleted,
            "files_unchanged": files_unchanged,
        },
    ).execute()

    logger.info("insert_codebase_version ended codebase_id=%s version=%s", codebase_id, version)


def get_next_version(supabase, codebase_id: str) -> int:
    """
    Get max version for codebase and return next (max + 1).
    Returns 1 if no versions exist.
    """
    r = (
        supabase.table("codebase_version")
        .select("version")
        .eq("codebase_id", codebase_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not r.data or len(r.data) == 0:
        return 1
    return int(r.data[0]["version"]) + 1
