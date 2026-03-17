-- Migration: 0004_query_log.sql
-- Records every query execution with its retrieval strategy, result metadata,
-- and latency measurements.
--
-- The `results` JSONB column stores result metadata only — no snippet text.
-- Snippets are fetched from Supabase Storage at query time and never persisted.
-- Each result object shape:
--   { rank, score, unit, kind, language, file, start_line, end_line, storage_ref }
--
-- client_latency_ms starts NULL and is filled in by a subsequent
-- PATCH /api/v1/query/{id}/telemetry call after the browser renders the results.

CREATE TABLE public.query_log (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    codebase_id         UUID        NOT NULL REFERENCES public.codebase(id) ON DELETE CASCADE,
    query_text          TEXT        NOT NULL,
    -- Retrieval strategy chosen by the LLM orchestrator
    strategy            TEXT        NOT NULL,
    -- Top-5 result metadata (no snippet text — fetched from Storage at query time)
    results             JSONB       NOT NULL DEFAULT '[]'::jsonb,
    -- Server-side: time from request receipt to response send
    backend_latency_ms  INT,
    -- Browser-side: time from submit click to first result paint (patched in post-render)
    client_latency_ms   INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ql_strategy_valid CHECK (strategy IN ('vector', 'graph', 'hybrid'))
);

CREATE INDEX idx_ql_user_id     ON public.query_log (user_id);
CREATE INDEX idx_ql_codebase_id ON public.query_log (codebase_id);
CREATE INDEX idx_ql_created_at  ON public.query_log (created_at DESC);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.query_log ENABLE ROW LEVEL SECURITY;

-- Users can read and write only their own query log rows.
CREATE POLICY "ql_select_owner"
ON public.query_log
FOR SELECT
USING (user_id = auth.uid());

CREATE POLICY "ql_insert_owner"
ON public.query_log
FOR INSERT
WITH CHECK (user_id = auth.uid());

-- Allows the telemetry PATCH to update client_latency_ms on the user's own rows.
CREATE POLICY "ql_update_owner"
ON public.query_log
FOR UPDATE
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

-- Admins can SELECT all query log rows (for aggregate analytics).
CREATE POLICY "ql_select_admin"
ON public.query_log
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);
