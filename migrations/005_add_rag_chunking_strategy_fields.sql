-- 005_add_rag_chunking_strategy_fields.sql

ALTER TABLE rag_documents
    ADD COLUMN IF NOT EXISTS chunk_strategy VARCHAR(32) NULL AFTER embedding_dimension,
    ADD COLUMN IF NOT EXISTS chunk_provider VARCHAR(64) NULL AFTER chunk_strategy,
    ADD COLUMN IF NOT EXISTS chunk_model VARCHAR(128) NULL AFTER chunk_provider,
    ADD COLUMN IF NOT EXISTS chunk_version VARCHAR(32) NULL AFTER chunk_model,
    ADD COLUMN IF NOT EXISTS chunk_fallback_used INT NOT NULL DEFAULT 0 AFTER chunk_version,
    ADD COLUMN IF NOT EXISTS chunk_fallback_reason VARCHAR(1024) NULL AFTER chunk_fallback_used;

ALTER TABLE rag_chunks
    ADD COLUMN IF NOT EXISTS topic VARCHAR(255) NULL AFTER section,
    ADD COLUMN IF NOT EXISTS summary LONGTEXT NULL AFTER topic,
    ADD COLUMN IF NOT EXISTS token_count INT NULL AFTER summary,
    ADD COLUMN IF NOT EXISTS start_offset INT NULL AFTER token_count,
    ADD COLUMN IF NOT EXISTS end_offset INT NULL AFTER start_offset,
    ADD COLUMN IF NOT EXISTS strategy_version VARCHAR(32) NULL AFTER end_offset;

ALTER TABLE rag_index_jobs
    ADD COLUMN IF NOT EXISTS requested_chunk_strategy VARCHAR(32) NULL AFTER chunks_count,
    ADD COLUMN IF NOT EXISTS applied_chunk_strategy VARCHAR(32) NULL AFTER requested_chunk_strategy,
    ADD COLUMN IF NOT EXISTS chunk_provider VARCHAR(64) NULL AFTER applied_chunk_strategy,
    ADD COLUMN IF NOT EXISTS chunk_model VARCHAR(128) NULL AFTER chunk_provider,
    ADD COLUMN IF NOT EXISTS chunk_version VARCHAR(32) NULL AFTER chunk_model,
    ADD COLUMN IF NOT EXISTS chunk_fallback_used INT NOT NULL DEFAULT 0 AFTER chunk_version,
    ADD COLUMN IF NOT EXISTS chunk_fallback_reason VARCHAR(1024) NULL AFTER chunk_fallback_used;

ALTER TABLE rag_query_logs
    ADD COLUMN IF NOT EXISTS chunk_strategy VARCHAR(32) NULL AFTER embedding_dimension,
    ADD COLUMN IF NOT EXISTS chunk_provider VARCHAR(64) NULL AFTER chunk_strategy,
    ADD COLUMN IF NOT EXISTS chunk_model VARCHAR(128) NULL AFTER chunk_provider;
