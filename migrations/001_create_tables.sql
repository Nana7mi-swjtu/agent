-- 001_create_tables.sql

CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS email_codes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255),
    expires_at DATETIME NOT NULL,
    used_at DATETIME,
    attempt_count INT NOT NULL DEFAULT 0,
    locked_until DATETIME,
    created_at DATETIME NOT NULL,
    INDEX idx_email_codes_email_purpose (email, purpose)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_users_email ON users (email);
