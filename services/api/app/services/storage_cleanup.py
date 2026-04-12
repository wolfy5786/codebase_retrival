"""
Delete Supabase Storage objects for a codebase using the service-role client.
Sources: keys from codebase_file_manifest.storage_ref (user client, RLS).
Zips: objects under codebases/{codebase_id}/ in codegraph-zips (admin list).
"""
import logging

logger = logging.getLogger(__name__)

SOURCES_BUCKET = "codegraph-sources"
ZIPS_BUCKET = "codegraph-zips"
REMOVE_BATCH = 1000
MANIFEST_PAGE = 1000


def _paginated_manifest_refs(supabase_user, codebase_id: str) -> list[str]:
    refs: list[str] = []
    offset = 0
    while True:
        r = (
            supabase_user.table("codebase_file_manifest")
            .select("storage_ref")
            .eq("codebase_id", codebase_id)
            .order("file_path", desc=False)
            .limit(MANIFEST_PAGE)
            .offset(offset)
            .execute()
        )
        rows = r.data or []
        if not rows:
            break
        for row in rows:
            refs.append(row["storage_ref"])
        if len(rows) < MANIFEST_PAGE:
            break
        offset += MANIFEST_PAGE
    return refs


def _batch_remove(bucket_api, paths: list[str]) -> None:
    if not paths:
        return
    for i in range(0, len(paths), REMOVE_BATCH):
        batch = paths[i : i + REMOVE_BATCH]
        bucket_api.remove(batch)


def _zip_object_keys(admin, codebase_id: str) -> list[str]:
    prefix = f"codebases/{codebase_id}"
    items = admin.storage.from_(ZIPS_BUCKET).list(prefix)
    if not items:
        return []
    keys: list[str] = []
    for item in items:
        name = item["name"]
        keys.append(f"{prefix}/{name}")
    return keys


def delete_codebase_storage(admin, supabase_user, codebase_id: str) -> None:
    """
    Remove indexed source files and uploaded ZIPs for this codebase.
    admin: Supabase client with service role (storage delete).
    supabase_user: user-scoped client (manifest SELECT under RLS).
    """
    logger.info("delete_codebase_storage started codebase_id=%s", codebase_id)

    refs = _paginated_manifest_refs(supabase_user, codebase_id)
    if refs:
        logger.info(
            "delete_codebase_storage removing %d manifest objects from %s",
            len(refs),
            SOURCES_BUCKET,
        )
        _batch_remove(admin.storage.from_(SOURCES_BUCKET), refs)

    zip_keys = _zip_object_keys(admin, codebase_id)
    if zip_keys:
        logger.info(
            "delete_codebase_storage removing %d objects from %s",
            len(zip_keys),
            ZIPS_BUCKET,
        )
        _batch_remove(admin.storage.from_(ZIPS_BUCKET), zip_keys)

    logger.info("delete_codebase_storage completed codebase_id=%s", codebase_id)
