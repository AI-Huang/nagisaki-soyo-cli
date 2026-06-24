CREATE DATABASE IF NOT EXISTS `nagisaki_soyo_digital_waifu`
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;

USE `nagisaki_soyo_digital_waifu`;

CREATE TABLE IF NOT EXISTS `raw_corpus_entries` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    `corpus_uid` CHAR(36) NOT NULL COMMENT 'Stable corpus entry identifier',
    `source_type` VARCHAR(32) NOT NULL COMMENT 'Source category such as manual, transcript, imported',
    `source_ref` VARCHAR(255) DEFAULT NULL COMMENT 'External reference or source file name',
    `scene` VARCHAR(64) DEFAULT NULL COMMENT 'Conversation scene or topic',
    `speaker_role` ENUM('system', 'user', 'assistant', 'narration') NOT NULL COMMENT 'Role in the dialogue',
    `speaker_name` VARCHAR(64) DEFAULT NULL COMMENT 'Display name for the speaker',
    `content` TEXT NOT NULL COMMENT 'Raw corpus text content',
    `emotion` VARCHAR(32) DEFAULT NULL COMMENT 'Optional emotion label',
    `style_label` VARCHAR(64) DEFAULT NULL COMMENT 'Optional style or persona tag',
    `language_code` VARCHAR(16) NOT NULL DEFAULT 'zh-CN' COMMENT 'BCP 47 style language code',
    `quality_score` DECIMAL(4,2) DEFAULT NULL COMMENT 'Manual quality score from 0 to 10',
    `safety_level` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 safe, larger values require review',
    `review_status` ENUM('draft', 'reviewing', 'approved', 'rejected', 'archived') NOT NULL DEFAULT 'draft' COMMENT 'Corpus review workflow status',
    `metadata` JSON DEFAULT NULL COMMENT 'Structured metadata such as tags, source attributes, or notes',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether the entry is active for downstream use',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_raw_corpus_entries_uid` (`corpus_uid`),
    KEY `idx_raw_corpus_entries_source_type` (`source_type`),
    KEY `idx_raw_corpus_entries_scene` (`scene`),
    KEY `idx_raw_corpus_entries_speaker_role` (`speaker_role`),
    KEY `idx_raw_corpus_entries_review_status` (`review_status`),
    KEY `idx_raw_corpus_entries_quality_score` (`quality_score`),
    KEY `idx_raw_corpus_entries_created_at` (`created_at`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='Original dialogue corpus table for the nagisaki_soyo_digital_waifu project';
