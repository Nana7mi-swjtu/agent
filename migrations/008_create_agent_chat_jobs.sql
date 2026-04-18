-- 008_create_agent_chat_jobs.sql

CREATE TABLE IF NOT EXISTS agent_chat_jobs (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(128) NOT NULL,
    message LONGTEXT NOT NULL,
    entity VARCHAR(255) NULL,
    intent VARCHAR(255) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    result_json JSON NULL,
    error_message VARCHAR(2048) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_agent_chat_jobs_user_id (user_id),
    INDEX ix_agent_chat_jobs_workspace_id (workspace_id),
    INDEX ix_agent_chat_jobs_role (role),
    INDEX ix_agent_chat_jobs_conversation_id (conversation_id),
    INDEX ix_agent_chat_jobs_status (status),
    INDEX ix_agent_chat_jobs_scope_status (user_id, workspace_id, role, conversation_id, status),
    INDEX ix_agent_chat_jobs_conversation_created (user_id, workspace_id, conversation_id, created_at),
    CONSTRAINT fk_agent_chat_jobs_user_id FOREIGN KEY (user_id) REFERENCES users (id)
);
