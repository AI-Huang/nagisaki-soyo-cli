CREATE DATABASE IF NOT EXISTS `nagisaki_soyo_digital_waifu`
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;

USE `nagisaki_soyo_digital_waifu`;

CREATE TABLE IF NOT EXISTS `llm_health` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    `provider_name` VARCHAR(64) NOT NULL COMMENT 'Provider or gateway name',
    `base_url` VARCHAR(255) DEFAULT NULL COMMENT 'OpenAI-compatible base URL used for the probe',
    `model_name` VARCHAR(128) NOT NULL COMMENT 'Model name that was tested',
    `probe_kind` VARCHAR(32) NOT NULL DEFAULT 'chat_completion' COMMENT 'Probe type such as chat_completion',
    `status` ENUM('ok', 'error') NOT NULL COMMENT 'Whether the model call succeeded',
    `is_available` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether the model is considered available for use',
    `response_preview` TEXT DEFAULT NULL COMMENT 'Short preview of the model response when successful',
    `error_type` VARCHAR(128) DEFAULT NULL COMMENT 'Exception type or gateway error type',
    `error_code` VARCHAR(128) DEFAULT NULL COMMENT 'Provider or gateway error code',
    `error_message` TEXT DEFAULT NULL COMMENT 'Error message when the probe failed',
    `http_status` INT DEFAULT NULL COMMENT 'HTTP or translated status code when known',
    `tested_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Probe timestamp',
    `metadata` JSON DEFAULT NULL COMMENT 'Additional probe metadata such as request ids or notes',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_llm_health_provider_model_tested_at` (`provider_name`, `model_name`, `tested_at`),
    KEY `idx_llm_health_model_name` (`model_name`),
    KEY `idx_llm_health_status` (`status`),
    KEY `idx_llm_health_is_available` (`is_available`),
    KEY `idx_llm_health_tested_at` (`tested_at`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='LLM availability and probe health records';
