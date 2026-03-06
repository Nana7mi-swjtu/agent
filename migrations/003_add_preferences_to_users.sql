-- 003_add_preferences_to_users.sql

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS preferences JSON NULL AFTER avatar_url;
