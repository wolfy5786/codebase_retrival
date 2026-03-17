-- Migration: 0002_codebase_file_manifest.sql
-- Tracks every indexed source file per codebase.
-- Serves two purposes:
--   1. Incremental update diffing: compare incoming content_hash against stored hash.
--   2. Locating the raw file in Supabase Storage via storage_ref.

CREATE TABLE public.codebase_file_manifest (
    id           UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    codebase_id  UUID        NOT NULL REFERENCES public.codebase(id) ON DELETE CASCADE,
    -- Relative path from repository root, e.g. "services/auth/src/jwt_utils.py"
    file_path    TEXT        NOT NULL,
    -- SHA-256 hex digest of file contents; used for change detection
    content_hash TEXT        NOT NULL,
    -- Supabase Storage object key: "codebases/{codebase_id}/files/{file_path}"
    storage_ref  TEXT        NOT NULL,
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Guarantees one manifest row per file path within a codebase
    CONSTRAINT cfm_codebase_file_unique UNIQUE (codebase_id, file_path)
);

-- Supporting index for full-codebase manifest reads (e.g. GET /codebases/{id}/manifest)
CREATE INDEX idx_cfm_codebase_id ON public.codebase_file_manifest (codebase_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.codebase_file_manifest ENABLE ROW LEVEL SECURITY;

-- Codebase owners can read the manifest.
-- NOTE: The granted-user clause (codebase_access subquery) is added by migration
-- 0007_codebase_access.sql, which drops and recreates this policy after the
-- codebase_access table exists.
CREATE POLICY "cfm_select_owner_or_granted"
ON public.codebase_file_manifest
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.codebase c
        WHERE c.id = codebase_id
          AND c.user_id = auth.uid()
    )
);

-- Admins can SELECT all manifest rows.
CREATE POLICY "cfm_select_admin"
ON public.codebase_file_manifest
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);

-- All writes (INSERT / UPDATE / DELETE) are performed by the indexer worker
-- using the service role key, which bypasses RLS entirely. No explicit
-- authenticated-user write policies are defined for this table.
