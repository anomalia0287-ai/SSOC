-- ============================================
--  공지 분류 봇 v4.0 — MySQL 초기 설정
--  실행: mysql -u root -p < init_db.sql
-- ============================================

CREATE DATABASE IF NOT EXISTS notice_bot
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'notice_bot'@'%'
  IDENTIFIED BY 'your_secure_password';

GRANT ALL PRIVILEGES ON notice_bot.* TO 'notice_bot'@'%';
FLUSH PRIVILEGES;

USE notice_bot;

-- 테이블은 앱 시작 시 db.init_pool()이 자동 생성합니다.
-- 수동으로 미리 만들고 싶다면 아래를 실행하세요.

CREATE TABLE IF NOT EXISTS channel_configs (
    channel_id  VARCHAR(32)  PRIMARY KEY,
    threshold   FLOAT        NOT NULL DEFAULT 0.85,
    digest_hour INT          NOT NULL DEFAULT 18,
    red_mention VARCHAR(16)  NOT NULL DEFAULT 'here',
    admin_users JSON,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS green_buffer (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    channel_id  VARCHAR(32)  NOT NULL,
    text        TEXT         NOT NULL,
    reason      VARCHAR(500),
    message_ts  VARCHAR(32),
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_channel (channel_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS classification_stats (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    channel_id  VARCHAR(32)  NOT NULL,
    stat_date   DATE         NOT NULL,
    grade       ENUM('RED','YELLOW','GREEN') NOT NULL,
    cnt         INT          NOT NULL DEFAULT 0,
    UNIQUE KEY  uq_ch_date_grade (channel_id, stat_date, grade),
    INDEX       idx_ch_date (channel_id, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS classification_log (
    id               BIGINT       AUTO_INCREMENT PRIMARY KEY,
    channel_id       VARCHAR(32)  NOT NULL,
    message_ts       VARCHAR(32),
    original_text    TEXT,
    grade            ENUM('RED','YELLOW','GREEN') NOT NULL,
    reason           VARCHAR(500),
    emoji            VARCHAR(16),
    stage2_used      BOOLEAN      DEFAULT FALSE,
    overridden       BOOLEAN      DEFAULT FALSE,
    override_reason  VARCHAR(500),
    reclassified_by  VARCHAR(64),
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_channel  (channel_id),
    INDEX idx_created  (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
