from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import (
    MYSQL_BIN,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    PROFILE_MYSQL_DATABASE,
    PROFILE_MYSQL_PERSONA_TABLE,
    PROFILE_MYSQL_USER_TABLE,
)
from .mysql_profile_source import MysqlProfileSource
from .profile_analysis import AnalysisResult


def persist_analysis_result_to_mysql(source: MysqlProfileSource, result: AnalysisResult) -> None:
    if not MYSQL_USER:
        raise RuntimeError("MYSQL_USER is required for MySQL persistence.")

    user_record = source.user_record
    source_snapshot = {
        "source_summary": result.source_summary,
        "feature_summary": result.feature_summary,
        "user_profile_facts": result.user_profile_facts,
        "matched_author_name": source.matched_author_name,
        "sample_count": result.sample_count,
    }
    interaction_traits = {
        "preferences": result.user_profile_facts["interaction_preferences"],
        "sensitivity_points": result.user_profile_facts["sensitivity_points"],
    }
    data_quality_score = round(result.confidence["overall"] * 10, 2)
    last_note_at = _normalize_datetime_sql(source.last_note_at)
    last_crawled_at = _normalize_datetime_sql(user_record.get("crawled_at"))
    generated_at = _normalize_datetime_sql(result.generated_at)

    query = f"""
INSERT INTO `{PROFILE_MYSQL_DATABASE}`.`{PROFILE_MYSQL_USER_TABLE}` (
    `profile_uid`,
    `source_platform`,
    `source_db`,
    `source_user_id`,
    `source_author_id`,
    `nickname`,
    `profile_url`,
    `bio`,
    `ip_location`,
    `follower_count`,
    `following_count`,
    `liked_count`,
    `note_count`,
    `comment_count`,
    `avg_note_length`,
    `last_note_at`,
    `last_crawled_at`,
    `source_snapshot`
) VALUES (
    {_sql_quote(str(uuid.uuid4()))},
    'xiaohongshu',
    'xhs_crawler',
    {_sql_quote(source.user_id)},
    {_nullable_sql(user_record.get('user_id'))},
    {_sql_quote(source.user_name)},
    {_nullable_sql(user_record.get('access_url'))},
    {_nullable_sql(user_record.get('bio'))},
    {_nullable_sql(user_record.get('ip_location'))},
    {_nullable_int_sql(_parse_metric_number(user_record.get('fans', '')))},
    {_nullable_int_sql(_parse_metric_number(user_record.get('follows', '')))},
    {_nullable_int_sql(_parse_metric_number(user_record.get('likes', '')))},
    {source.note_count},
    {source.comment_count},
    {_nullable_int_sql(source.avg_note_length)},
    {last_note_at},
    {last_crawled_at},
    {_json_sql(source_snapshot)}
) ON DUPLICATE KEY UPDATE
    `id` = LAST_INSERT_ID(`id`),
    `profile_uid` = VALUES(`profile_uid`),
    `source_author_id` = VALUES(`source_author_id`),
    `nickname` = VALUES(`nickname`),
    `profile_url` = VALUES(`profile_url`),
    `bio` = VALUES(`bio`),
    `ip_location` = VALUES(`ip_location`),
    `follower_count` = VALUES(`follower_count`),
    `following_count` = VALUES(`following_count`),
    `liked_count` = VALUES(`liked_count`),
    `note_count` = VALUES(`note_count`),
    `comment_count` = VALUES(`comment_count`),
    `avg_note_length` = VALUES(`avg_note_length`),
    `last_note_at` = VALUES(`last_note_at`),
    `last_crawled_at` = VALUES(`last_crawled_at`),
    `source_snapshot` = VALUES(`source_snapshot`);

SET @user_profile_id = LAST_INSERT_ID();

INSERT INTO `{PROFILE_MYSQL_DATABASE}`.`{PROFILE_MYSQL_PERSONA_TABLE}` (
    `summary_uid`,
    `user_profile_id`,
    `persona_summary`,
    `agent_strategy`,
    `prompt_profile`,
    `source_summary`,
    `feature_summary`,
    `user_profile_facts`,
    `interaction_traits`,
    `evidence`,
    `confidence`,
    `generation_mode`,
    `llm_model`,
    `portrait_version`,
    `data_quality_score`,
    `generated_at`
) VALUES (
    {_sql_quote(str(uuid.uuid4()))},
    @user_profile_id,
    {_sql_quote(result.persona_summary)},
    {_json_sql(result.agent_strategy)},
    {_sql_quote(result.prompt_profile)},
    {_json_sql(result.source_summary)},
    {_json_sql(result.feature_summary)},
    {_json_sql(result.user_profile_facts)},
    {_json_sql(interaction_traits)},
    {_json_sql(result.evidence)},
    {_json_sql(result.confidence)},
    {_sql_quote(result.generation_mode)},
    {_nullable_sql(result.model_name)},
    'v2',
    {data_quality_score},
    {generated_at}
) ON DUPLICATE KEY UPDATE
    `summary_uid` = VALUES(`summary_uid`),
    `persona_summary` = VALUES(`persona_summary`),
    `agent_strategy` = VALUES(`agent_strategy`),
    `prompt_profile` = VALUES(`prompt_profile`),
    `source_summary` = VALUES(`source_summary`),
    `feature_summary` = VALUES(`feature_summary`),
    `user_profile_facts` = VALUES(`user_profile_facts`),
    `interaction_traits` = VALUES(`interaction_traits`),
    `evidence` = VALUES(`evidence`),
    `confidence` = VALUES(`confidence`),
    `generation_mode` = VALUES(`generation_mode`),
    `llm_model` = VALUES(`llm_model`),
    `portrait_version` = VALUES(`portrait_version`),
    `data_quality_score` = VALUES(`data_quality_score`),
    `generated_at` = VALUES(`generated_at`);
"""
    _run_mysql(query)


def _run_mysql(query: str) -> None:
    command = [
        MYSQL_BIN,
        "--protocol=TCP",
        f"-h{MYSQL_HOST}",
        f"-P{MYSQL_PORT}",
        f"-u{MYSQL_USER}",
        "--batch",
        "--raw",
        "-e",
        " ".join(line.strip() for line in query.strip().splitlines()),
    ]
    env = os.environ.copy()
    if MYSQL_PASSWORD:
        env["MYSQL_PWD"] = MYSQL_PASSWORD
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"MySQL persistence failed: {completed.stderr.strip() or 'Unknown MySQL error.'}")


def _sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _nullable_sql(value: str | None) -> str:
    if value is None or not value.strip():
        return "NULL"
    return _sql_quote(value)


def _nullable_int_sql(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _json_sql(value: Any) -> str:
    return _sql_quote(json.dumps(value, ensure_ascii=False))


def _parse_metric_number(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    number = float(match.group(1))
    if "万" in text.lower():
        number *= 10000
    elif "k" in text.lower():
        number *= 1000
    return int(number)


def _normalize_datetime_sql(raw: str | None) -> str:
    normalized = _normalize_datetime_value(raw)
    return "NULL" if normalized is None else _sql_quote(normalized)


def _normalize_datetime_value(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        timestamp = float(text)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                return parsed.strftime("%Y-%m-%d 00:00:00")
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None
