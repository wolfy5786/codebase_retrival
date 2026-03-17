-- Migration: 0005_query_feedback.sql
-- Optional per-query relevancy ratings submitted by users after results are rendered.
-- One rating per user per query (enforced by unique constraint).

CREATE TABLE public.query_feedback (
    id         UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    query_id   UUID        NOT NULL REFERENCES public.query_log(id) ON DELETE CASCADE,
    user_id    UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Relevancy score on a 1–10 scale
    rating     SMALLINT    NOT NULL,
    -- Optional free-text comment from the user
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT qf_rating_range CHECK (rating BETWEEN 1 AND 10),
    -- One rating per user per query; prevents duplicate submissions
    CONSTRAINT qf_query_user_unique UNIQUE (query_id, user_id)
);

CREATE INDEX idx_qf_query_id ON public.query_feedback (query_id);
CREATE INDEX idx_qf_user_id  ON public.query_feedback (user_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.query_feedback ENABLE ROW LEVEL SECURITY;

-- Users can read their own feedback submissions.
CREATE POLICY "qf_select_owner"
ON public.query_feedback
FOR SELECT
USING (user_id = auth.uid());

-- Users can submit feedback only under their own user_id.
CREATE POLICY "qf_insert_owner"
ON public.query_feedback
FOR INSERT
WITH CHECK (user_id = auth.uid());

-- Admins can SELECT all feedback rows (for aggregate analytics / rating summaries).
CREATE POLICY "qf_select_admin"
ON public.query_feedback
FOR SELECT
USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
);
