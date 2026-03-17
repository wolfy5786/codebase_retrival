-- Migration: 0003_codebase_versions.sql
-- Records one version entry per upload that results in at least one file change.
-- Provides a git-like history of what changed in each ingestion run.

CREATE TABLE public.codebase_version (
    id               UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    codebase_id      UUID        NOT NULL REFERENCES public.codebase(id) ON DELETE CASCADE,
    -- Monotonically incrementing integer within each codebase (starts at 1)
    version          INT         NOT NULL,
    -- Source of this upload: zip | github | local
    upload_source    TEXT        NOT NULL,
    files_added      INT         NOT NULL DEFAULT 0,
    files_modified   INT         NOT NULL DEFAULT 0,
    files_deleted    INT         NOT NULL DEFAULT 0,
    files_unchanged  INT         NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cv_codebase_version_unique UNIQUE (codebase_id, version),
    CONSTRAINT cv_upload_source_valid CHECK (upload_source IN ('zip', 'github', 'local')),
    CONSTRAINT cv_files_added_nonneg    CHECK (files_added    >= 0),
    CONSTRAINT cv_files_modified_nonneg CHECK (files_modified >= 0),
    CONSTRAINT cv_files_deleted_nonneg  CHECK (files_deleted  >= 0),
    CONSTRAINT cv_files_unchanged_nonneg CHECK (files_unchanged >= 0)
);

-- Supports version history reads ordered by most recent first
CREATE INDEX idx_cv_codebase_version ON public.codebase_version (codebase_id, version DESC);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.codebase_version ENABLE ROW LEVEL SECURITY;

-- Codebase owners can read version history.
-- NOTE: The granted-user clause (codebase_access subquery) is added by migration
-- 0007_codebase_access.sql, which drops and recreates this policy after the
-- codebase_access table exists.
CREATE POLICY "cv_select_owner_or_granted"
ON public.codebase_version
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.codebase c
        WHERE c.id = codebase_id
          AND c.user_id = auth.uid()
    )
);

-- Admins can SELECT all version rows.
CREATE POLICY "cv_select_admin"
ON public.codebase_version
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);

-- All writes are performed by the indexer worker via service role key (bypasses RLS).
