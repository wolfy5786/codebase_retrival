-- Migration: 0006_ingestion_log.sql
-- Records every ingestion job from creation through completion.
-- The `status` column is updated in-place by the indexer worker as the job progresses.
-- All writes from the indexer use the service role key (bypasses RLS).

CREATE TABLE public.ingestion_log (
    id                    UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    codebase_id           UUID        NOT NULL REFERENCES public.codebase(id) ON DELETE CASCADE,
    user_id               UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Source type for this ingestion run: zip | github | local
    source_type           TEXT        NOT NULL,
    -- Job lifecycle state; updated in-place by the indexer worker
    status                TEXT        NOT NULL DEFAULT 'pending',
    -- Total source files scanned (set on completion)
    file_count            INT,
    -- Total Neo4j nodes written (set on completion)
    node_count            INT,
    -- Wall-clock time from job dequeue to final Neo4j write, in milliseconds
    ingestion_latency_ms  INT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULL until the job reaches a terminal state (completed or failed)
    completed_at          TIMESTAMPTZ,

    CONSTRAINT il_source_type_valid CHECK (source_type IN ('zip', 'github', 'local')),
    CONSTRAINT il_status_valid CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT il_file_count_nonneg CHECK (file_count IS NULL OR file_count >= 0),
    CONSTRAINT il_node_count_nonneg CHECK (node_count IS NULL OR node_count >= 0),
    CONSTRAINT il_latency_nonneg    CHECK (ingestion_latency_ms IS NULL OR ingestion_latency_ms >= 0)
);

CREATE INDEX idx_il_codebase_id  ON public.ingestion_log (codebase_id);
CREATE INDEX idx_il_user_id      ON public.ingestion_log (user_id);
CREATE INDEX idx_il_status       ON public.ingestion_log (status);
CREATE INDEX idx_il_started_at   ON public.ingestion_log (started_at DESC);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.ingestion_log ENABLE ROW LEVEL SECURITY;

-- Users can read their own ingestion job rows.
CREATE POLICY "il_select_owner"
ON public.ingestion_log
FOR SELECT
USING (user_id = auth.uid());

-- Users can create ingestion jobs under their own user_id (API layer inserts the
-- initial pending row before enqueuing to Redis).
CREATE POLICY "il_insert_owner"
ON public.ingestion_log
FOR INSERT
WITH CHECK (user_id = auth.uid());

-- The indexer worker updates status, counts, and timestamps via service role
-- key (bypasses RLS). The policy below covers any non-service-role UPDATE path
-- (e.g. a future cancel endpoint initiated by the owning user).
CREATE POLICY "il_update_owner"
ON public.ingestion_log
FOR UPDATE
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

-- Admins can SELECT all ingestion log rows (for aggregate analytics).
CREATE POLICY "il_select_admin"
ON public.ingestion_log
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);
