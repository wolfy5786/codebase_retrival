-- Create the Storage bucket used by the API for ZIP uploads (codegraph-zips).
-- Required for POST /api/v1/codebases/{id}/ingest (ZIP upload path).
-- See: src.config.settings.supabase_storage_bucket_zips (default: codegraph-zips)

INSERT INTO storage.buckets (id, name, public)
VALUES ('codegraph-zips', 'codegraph-zips', false)
ON CONFLICT (id) DO NOTHING;
