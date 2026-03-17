-- Migration: 0001_codebases.sql
-- Creates the central `codebase` table that every other entity references.

CREATE TABLE public.codebase (
    id          UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT        NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT codebase_user_name_unique UNIQUE (user_id, name)
);

-- Index for per-user codebase lookups
CREATE INDEX idx_codebase_user_id ON public.codebase (user_id);

-- Keep updated_at current on every row update
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_codebase_updated_at
BEFORE UPDATE ON public.codebase
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.codebase ENABLE ROW LEVEL SECURITY;

-- Owners can see their own codebases.
-- NOTE: The granted-user clause (codebase_access subquery) is added by migration
-- 0007_codebase_access.sql, which drops and recreates this policy after the
-- codebase_access table exists. PostgreSQL validates relation references in
-- USING clauses at DDL time, so we cannot reference codebase_access here.
CREATE POLICY "codebase_select_owner_or_granted"
ON public.codebase
FOR SELECT
USING (
    user_id = auth.uid()
);

-- Admins can SELECT all codebases.
CREATE POLICY "codebase_select_admin"
ON public.codebase
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);

-- Only the owner can create a codebase under their own user_id.
CREATE POLICY "codebase_insert_owner"
ON public.codebase
FOR INSERT
WITH CHECK (user_id = auth.uid());

-- Only the owner can update their own codebase.
CREATE POLICY "codebase_update_owner"
ON public.codebase
FOR UPDATE
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

-- Only the owner can delete their own codebase.
CREATE POLICY "codebase_delete_owner"
ON public.codebase
FOR DELETE
USING (user_id = auth.uid());
