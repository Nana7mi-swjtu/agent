-- 007_scope_agent_memory_by_conversation.sql

ALTER TABLE agent_conversation_threads
    ADD COLUMN conversation_id VARCHAR(128) NOT NULL AFTER role;

ALTER TABLE agent_conversation_threads
    DROP INDEX uq_agent_conversation_threads_scope;

ALTER TABLE agent_conversation_threads
    ADD UNIQUE KEY uq_agent_conversation_threads_scope (user_id, workspace_id, role, conversation_id);
