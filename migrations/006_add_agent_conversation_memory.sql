-- 006_add_agent_conversation_memory.sql

CREATE TABLE IF NOT EXISTS agent_conversation_threads (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL,
    summary LONGTEXT NULL,
    last_user_message LONGTEXT NULL,
    last_assistant_message LONGTEXT NULL,
    last_intent VARCHAR(64) NULL,
    last_clarification_question LONGTEXT NULL,
    turn_count INT NOT NULL DEFAULT 0,
    last_message_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_agent_conversation_threads_scope (user_id, workspace_id, role),
    INDEX idx_agent_conversation_threads_user_id (user_id),
    INDEX idx_agent_conversation_threads_workspace_id (workspace_id),
    INDEX idx_agent_conversation_threads_role (role),
    CONSTRAINT fk_agent_conversation_threads_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_conversation_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    workspace_id VARCHAR(128) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content LONGTEXT NOT NULL,
    intent VARCHAR(64) NULL,
    metadata_json JSON NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_agent_conversation_messages_thread_id (thread_id),
    INDEX idx_agent_conversation_messages_user_id (user_id),
    INDEX idx_agent_conversation_messages_workspace_id (workspace_id),
    INDEX idx_agent_conversation_messages_role (role),
    CONSTRAINT fk_agent_conversation_messages_thread FOREIGN KEY (thread_id) REFERENCES agent_conversation_threads(id),
    CONSTRAINT fk_agent_conversation_messages_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
