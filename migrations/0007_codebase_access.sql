-- Migration: 0007_codebase_access.sql
-- Records admin-granted cross-user access to codebases.
-- Required by: POST /api/v1/admin/codebases/{id}/grant
--
-- This table is intentionally written-to only via the service role key
-- (admin operations). Regular users can SELECT their own grants to discover
-- which codebases they have been given access to.
--
-- The codebase SELECT and codebase_file_manifest SELECT policies in earlier
-- migrations reference this table via EXISTS subqueries to extend read access
-- to grantees.

CREATE TABLE public.codebase_access (
    id           UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    codebase_id  UUID        NOT NULL REFERENCES public.codebase(id) ON DELETE CASCADE,
    -- The user being granted access
    user_id      UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- The admin who created this grant
    granted_by   UUID        NOT NULL REFERENCES auth.users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One grant per user per codebase; duplicate grants are idempotent
    CONSTRAINT ca_codebase_user_unique UNIQUE (codebase_id, user_id)
);

CREATE INDEX idx_ca_codebase_id ON public.codebase_access (codebase_id);
CREATE INDEX idx_ca_user_id     ON public.codebase_access (user_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.codebase_access ENABLE ROW LEVEL SECURITY;

-- Grantees can see grants that apply to them (so the UI can show
-- "shared with you" codebases).
CREATE POLICY "ca_select_grantee"
ON public.codebase_access
FOR SELECT
USING (user_id = auth.uid());

-- Codebase owners can see who has been granted access to their codebases.
CREATE POLICY "ca_select_codebase_owner"
ON public.codebase_access
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.codebase c
        WHERE c.id = codebase_id
          AND c.user_id = auth.uid()
    )
);

-- Admins can SELECT all access grants.
CREATE POLICY "ca_select_admin"
ON public.codebase_access
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);

-- INSERT and DELETE are performed only by admins via the service role key,
-- which bypasses RLS entirely. No authenticated-user write policies are defined.

-- ---------------------------------------------------------------------------
-- Upgrade policies on dependent tables to include granted-user access.
-- Now that codebase_access exists, we can drop and recreate the owner-only
-- SELECT policies from migrations 0001–0003 with the full subquery.
-- ---------------------------------------------------------------------------

-- codebase: replace owner-only SELECT with owner-or-granted SELECT
DROP POLICY IF EXISTS "codebase_select_owner_or_granted" ON public.codebase;
CREATE POLICY "codebase_select_owner_or_granted"
ON public.codebase
FOR SELECT
USING (
    user_id = auth.uid()
    OR EXISTS (
        SELECT 1
        FROM public.codebase_access ca
        WHERE ca.codebase_id = id
          AND ca.user_id = auth.uid()
    )
);

-- codebase_file_manifest: replace owner-only SELECT with owner-or-granted SELECT
DROP POLICY IF EXISTS "cfm_select_owner_or_granted" ON public.codebase_file_manifest;
CREATE POLICY "cfm_select_owner_or_granted"
ON public.codebase_file_manifest
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.codebase c
        WHERE c.id = codebase_id
          AND (
              c.user_id = auth.uid()
              OR EXISTS (
                  SELECT 1
                  FROM public.codebase_access ca
                  WHERE ca.codebase_id = c.id
                    AND ca.user_id = auth.uid()
              )
          )
    )
);

-- codebase_version: replace owner-only SELECT with owner-or-granted SELECT
DROP POLICY IF EXISTS "cv_select_owner_or_granted" ON public.codebase_version;
CREATE POLICY "cv_select_owner_or_granted"
ON public.codebase_version
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.codebase c
        WHERE c.id = codebase_id
          AND (
              c.user_id = auth.uid()
              OR EXISTS (
                  SELECT 1
                  FROM public.codebase_access ca
                  WHERE ca.codebase_id = c.id
                    AND ca.user_id = auth.uid()
              )
          )
    )
);
