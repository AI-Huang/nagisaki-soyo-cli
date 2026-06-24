CREATE DATABASE IF NOT EXISTS `nagisaki_soyo_digital_waifu`
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;

USE `nagisaki_soyo_digital_waifu`;

CREATE TABLE IF NOT EXISTS `user_profiles` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    `profile_uid` CHAR(36) NOT NULL COMMENT 'Stable profile snapshot identifier',
    `source_platform` VARCHAR(32) NOT NULL DEFAULT 'xiaohongshu' COMMENT 'Source platform name',
    `source_db` VARCHAR(64) NOT NULL DEFAULT 'xhs_crawler' COMMENT 'Source crawl database name',
    `source_user_id` VARCHAR(64) NOT NULL COMMENT 'User identifier from xhs_crawler.users',
    `source_author_id` VARCHAR(64) DEFAULT NULL COMMENT 'Author identifier when authors and users are separated',
    `nickname` VARCHAR(128) NOT NULL COMMENT 'Current nickname or display name',
    `profile_url` VARCHAR(255) DEFAULT NULL COMMENT 'Canonical user profile URL',
    `bio` TEXT DEFAULT NULL COMMENT 'Profile description or signature',
    `ip_location` VARCHAR(64) DEFAULT NULL COMMENT 'IP or recent location label',
    `follower_count` INT UNSIGNED DEFAULT NULL COMMENT 'Followers count',
    `following_count` INT UNSIGNED DEFAULT NULL COMMENT 'Following count',
    `liked_count` INT UNSIGNED DEFAULT NULL COMMENT 'Likes or receives-like count',
    `note_count` INT UNSIGNED DEFAULT NULL COMMENT 'Published note count',
    `comment_count` INT UNSIGNED DEFAULT NULL COMMENT 'Observed comment count',
    `avg_note_length` INT UNSIGNED DEFAULT NULL COMMENT 'Average note text length',
    `last_note_at` DATETIME DEFAULT NULL COMMENT 'Latest observed note publish time',
    `last_crawled_at` DATETIME DEFAULT NULL COMMENT 'Latest crawl sync time',
    `source_snapshot` JSON DEFAULT NULL COMMENT 'Original extracted fields from xhs_crawler tables',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_profiles_uid` (`profile_uid`),
    UNIQUE KEY `uk_user_profiles_source_user` (`source_platform`, `source_user_id`),
    KEY `idx_user_profiles_nickname` (`nickname`),
    KEY `idx_user_profiles_ip_location` (`ip_location`),
    KEY `idx_user_profiles_follower_count` (`follower_count`),
    KEY `idx_user_profiles_note_count` (`note_count`),
    KEY `idx_user_profiles_last_note_at` (`last_note_at`),
    KEY `idx_user_profiles_last_crawled_at` (`last_crawled_at`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='Platform user metadata for Xiaohongshu users synchronized from xhs_crawler';

CREATE TABLE IF NOT EXISTS `persona_summaries` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    `summary_uid` CHAR(36) NOT NULL COMMENT 'Stable persona summary snapshot identifier',
    `user_profile_id` BIGINT UNSIGNED NOT NULL COMMENT 'Foreign key to user_profiles.id',
    `persona_summary` TEXT DEFAULT NULL COMMENT 'Structured natural-language user portrait',
    `agent_strategy` JSON DEFAULT NULL COMMENT 'Agent strategy derived from the user portrait',
    `prompt_profile` TEXT DEFAULT NULL COMMENT 'Prompt-ready user profile summary',
    `source_summary` JSON DEFAULT NULL COMMENT 'Input source counts used during analysis',
    `feature_summary` JSON DEFAULT NULL COMMENT 'Computed feature metrics from the text samples',
    `user_profile_facts` JSON DEFAULT NULL COMMENT 'Structured facts inferred from the source texts',
    `interaction_traits` JSON DEFAULT NULL COMMENT 'Interaction style inferred from the analysis result',
    `evidence` JSON DEFAULT NULL COMMENT 'Evidence snippets and signals supporting the portrait',
    `confidence` JSON DEFAULT NULL COMMENT 'Confidence scores for generated portrait artifacts',
    `generation_mode` VARCHAR(16) NOT NULL DEFAULT 'rule' COMMENT 'Generation mode such as rule or llm',
    `llm_model` VARCHAR(128) DEFAULT NULL COMMENT 'LLM model name when the portrait is model-generated',
    `portrait_version` VARCHAR(32) NOT NULL DEFAULT 'v2' COMMENT 'Portrait generation schema version',
    `data_quality_score` DECIMAL(4,2) DEFAULT NULL COMMENT 'Manual or automated quality score',
    `generated_at` DATETIME DEFAULT NULL COMMENT 'Profile bundle generation time',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_persona_summaries_uid` (`summary_uid`),
    UNIQUE KEY `uk_persona_summaries_user_profile` (`user_profile_id`),
    KEY `idx_persona_summaries_generation_mode` (`generation_mode`),
    KEY `idx_persona_summaries_llm_model` (`llm_model`),
    KEY `idx_persona_summaries_generated_at` (`generated_at`),
    CONSTRAINT `fk_persona_summaries_user_profile`
        FOREIGN KEY (`user_profile_id`) REFERENCES `user_profiles` (`id`)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='LLM and rule-generated persona summaries linked to user_profiles';
