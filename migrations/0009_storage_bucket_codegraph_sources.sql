-- Create the Storage bucket used by the indexer for indexed source files (storage_ref).
-- Required for the ingestion pipeline after ZIP extract (StorageUploader).
-- See: services/indexer src.config.settings.supabase_storage_bucket (default: codegraph-sources)

INSERT INTO storage.buckets (id, name, public)
VALUES ('codegraph-sources', 'codegraph-sources', false)
ON CONFLICT (id) DO NOTHING;
