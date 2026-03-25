-- 004_add_rag_tables.sql

CREATE TABLE IF NOT EXISTS rag_documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_extension VARCHAR(16) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    error_message VARCHAR(2048) NULL,
    embedding_model VARCHAR(128) NULL,
    embedding_version VARCHAR(64) NULL,
    embedding_dimension INT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    indexed_at DATETIME NULL,
    deleted_at DATETIME NULL,
    INDEX idx_rag_documents_user_id (user_id),
    INDEX idx_rag_documents_workspace_id (workspace_id),
    INDEX idx_rag_documents_status (status),
    CONSTRAINT fk_rag_documents_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    chunk_id VARCHAR(64) NOT NULL UNIQUE,
    content LONGTEXT NOT NULL,
    source VARCHAR(255) NOT NULL,
    page INT NULL,
    section VARCHAR(255) NULL,
    metadata_json JSON NULL,
    embedding_model VARCHAR(128) NOT NULL,
    embedding_version VARCHAR(64) NOT NULL,
    embedding_dimension INT NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_rag_chunks_document_id (document_id),
    INDEX idx_rag_chunks_user_id (user_id),
    INDEX idx_rag_chunks_workspace_id (workspace_id),
    CONSTRAINT fk_rag_chunks_document FOREIGN KEY (document_id) REFERENCES rag_documents(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rag_index_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_stage VARCHAR(64) NULL,
    error_message VARCHAR(2048) NULL,
    chunks_count INT NOT NULL DEFAULT 0,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    duration_ms INT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_rag_index_jobs_document_id (document_id),
    INDEX idx_rag_index_jobs_user_id (user_id),
    INDEX idx_rag_index_jobs_workspace_id (workspace_id),
    INDEX idx_rag_index_jobs_status (status),
    CONSTRAINT fk_rag_index_jobs_document FOREIGN KEY (document_id) REFERENCES rag_documents(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rag_query_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    query_text LONGTEXT NOT NULL,
    top_k INT NOT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    latency_ms INT NOT NULL DEFAULT 0,
    top_scores JSON NULL,
    filters JSON NULL,
    vector_provider VARCHAR(64) NOT NULL,
    embedder_provider VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(128) NOT NULL,
    embedding_version VARCHAR(64) NOT NULL,
    embedding_dimension INT NOT NULL,
    failure_reason VARCHAR(1024) NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_rag_query_logs_user_id (user_id),
    INDEX idx_rag_query_logs_workspace_id (workspace_id),
    INDEX idx_rag_query_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
