from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import (
    MYSQL_USER,
    PROFILE_MYSQL_DATABASE,
    PROFILE_MYSQL_PERSONA_TABLE,
    PROFILE_MYSQL_USER_TABLE,
)
from .mysql_profile_source import _decode_hex, _run_mysql_tsv, _sql_quote


@dataclass
class PersonaMirrorSource:
    source_user_id: str
    user_name: str
    bio: str
    persona_summary: str
    agent_strategy: dict[str, Any]
    prompt_profile: str
    confidence: dict[str, Any]
    generation_mode: str
    llm_model: str | None
    generated_at: str | None


def load_persona_mirror_source(
    *,
    user_name: str | None,
    user_id: str | None,
) -> PersonaMirrorSource:
    if not MYSQL_USER:
        raise RuntimeError("MYSQL_USER is required for demo-chat.")

    where_clauses: list[str] = []
    if user_id:
        where_clauses.append(f"up.source_user_id = {_sql_quote(user_id)}")
    if user_name:
        where_clauses.append(f"up.nickname = {_sql_quote(user_name)}")
    if not where_clauses:
        raise RuntimeError("Either user_name or user_id is required.")

    query = f"""
SELECT
    HEX(up.source_user_id),
    HEX(up.nickname),
    HEX(COALESCE(up.bio, '')),
    HEX(COALESCE(ps.persona_summary, '')),
    HEX(COALESCE(CAST(ps.agent_strategy AS CHAR), '')),
    HEX(COALESCE(ps.prompt_profile, '')),
    HEX(COALESCE(CAST(ps.confidence AS CHAR), '')),
    HEX(COALESCE(ps.generation_mode, '')),
    HEX(COALESCE(ps.llm_model, '')),
    HEX(COALESCE(CAST(ps.generated_at AS CHAR), ''))
FROM `{PROFILE_MYSQL_DATABASE}`.`{PROFILE_MYSQL_USER_TABLE}` AS up
INNER JOIN `{PROFILE_MYSQL_DATABASE}`.`{PROFILE_MYSQL_PERSONA_TABLE}` AS ps
    ON ps.user_profile_id = up.id
WHERE {" OR ".join(where_clauses)}
ORDER BY COALESCE(ps.generated_at, ps.updated_at, ps.created_at) DESC
LIMIT 1
"""
    rows = _run_mysql_tsv(query, expected_columns=10)
    if not rows:
        raise RuntimeError("No matching persisted persona summary was found for demo-chat.")

    row = rows[0]
    agent_strategy = _loads_json(_decode_hex(row[4]), field_name="agent_strategy")
    confidence = _loads_json(_decode_hex(row[6]), field_name="confidence")
    return PersonaMirrorSource(
        source_user_id=_decode_hex(row[0]),
        user_name=_decode_hex(row[1]),
        bio=_decode_hex(row[2]),
        persona_summary=_decode_hex(row[3]),
        agent_strategy=agent_strategy,
        prompt_profile=_decode_hex(row[5]),
        confidence=confidence,
        generation_mode=_decode_hex(row[7]) or "unknown",
        llm_model=_decode_hex(row[8]) or None,
        generated_at=_decode_hex(row[9]) or None,
    )


def _loads_json(raw: str, *, field_name: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode persisted {field_name} JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Persisted {field_name} must be a JSON object.")
    return value
