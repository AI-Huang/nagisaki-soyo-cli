from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from .config import (
    LLM_HEALTH_TABLE,
    MYSQL_BIN,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PROFILE_MYSQL_DATABASE,
)

DEFAULT_LLM_HEALTH_MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5-chat-latest",
]


@dataclass
class LlmHealthRecord:
    provider_name: str
    base_url: str | None
    model_name: str
    probe_kind: str
    status: str
    is_available: bool
    response_preview: str | None
    error_type: str | None
    error_code: str | None
    error_message: str | None
    http_status: int | None
    metadata: dict[str, Any]
    tested_at: str


@dataclass
class LlmHealthProbeResult:
    provider_name: str
    base_url: str | None
    visible_models: list[str]
    records: list[LlmHealthRecord]
    generated_at: str


def run_llm_health_probe(
    *,
    models: list[str],
    request_text: str = "Reply with ok",
    temperature: float = 0,
    fetch_visible_models: bool = True,
) -> LlmHealthProbeResult:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for llm-health-probe.")
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    visible_models = _list_visible_models(client) if fetch_visible_models else []
    provider_name = _provider_name_from_base_url(OPENAI_BASE_URL)
    records = [
        _probe_one_model(
            client,
            provider_name=provider_name,
            model_name=model_name,
            request_text=request_text,
            temperature=temperature,
        )
        for model_name in models
    ]
    return LlmHealthProbeResult(
        provider_name=provider_name,
        base_url=OPENAI_BASE_URL,
        visible_models=visible_models,
        records=records,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def persist_llm_health_records(result: LlmHealthProbeResult) -> None:
    if not MYSQL_USER:
        raise RuntimeError("MYSQL_USER is required for llm_health persistence.")
    if not result.records:
        return
    values = []
    for record in result.records:
        values.append(
            "("
            f"{_sql_quote(record.provider_name)}, "
            f"{_nullable_sql(record.base_url)}, "
            f"{_sql_quote(record.model_name)}, "
            f"{_sql_quote(record.probe_kind)}, "
            f"{_sql_quote(record.status)}, "
            f"{1 if record.is_available else 0}, "
            f"{_nullable_sql(record.response_preview)}, "
            f"{_nullable_sql(record.error_type)}, "
            f"{_nullable_sql(record.error_code)}, "
            f"{_nullable_sql(record.error_message)}, "
            f"{_nullable_int_sql(record.http_status)}, "
            f"{_sql_quote(record.tested_at.replace('T', ' ').replace('+00:00', ''))}, "
            f"{_json_sql(record.metadata)}"
            ")"
        )
    query = f"""
INSERT INTO `{PROFILE_MYSQL_DATABASE}`.`{LLM_HEALTH_TABLE}` (
    `provider_name`,
    `base_url`,
    `model_name`,
    `probe_kind`,
    `status`,
    `is_available`,
    `response_preview`,
    `error_type`,
    `error_code`,
    `error_message`,
    `http_status`,
    `tested_at`,
    `metadata`
) VALUES
{", ".join(values)};
"""
    _run_mysql(query)


def format_llm_health_summary(result: LlmHealthProbeResult) -> str:
    lines = [
        f"provider_name: {result.provider_name}",
        f"base_url: {result.base_url or 'unset'}",
        f"visible_models_count: {len(result.visible_models)}",
        "probe_results:",
    ]
    for record in result.records:
        summary = (
            record.response_preview or record.error_code or record.error_type or "-"
        )
        lines.append(
            f"- {record.model_name} | {record.status} | available={1 if record.is_available else 0} | http_status={record.http_status or '-'} | {summary}"
        )
    return "\n".join(lines)


def _list_visible_models(client: OpenAI) -> list[str]:
    try:
        models = client.models.list()
    except Exception:
        return []
    return sorted(
        {
            model.id
            for model in models.data
            if "gpt-4" in model.id or "gpt-5" in model.id
        }
    )


def list_available_chat_models() -> list[str]:
    """Return chat model names for interactive selection.

    Tries the live provider model list first and falls back to the curated
    default health-probe models when the provider call is unavailable.
    """
    if OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
            visible = _list_visible_models(client)
        except Exception:
            visible = []
        if visible:
            return visible
    return list(DEFAULT_LLM_HEALTH_MODELS)


def _probe_one_model(
    client: OpenAI,
    *,
    provider_name: str,
    model_name: str,
    request_text: str,
    temperature: float,
) -> LlmHealthRecord:
    tested_at = datetime.now(timezone.utc).isoformat()
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": request_text}],
            temperature=temperature,
        )
        preview = None
        if getattr(response, "choices", None):
            preview = (response.choices[0].message.content or "").strip().replace(
                "\n", " "
            )[:160] or None
        return LlmHealthRecord(
            provider_name=provider_name,
            base_url=OPENAI_BASE_URL,
            model_name=model_name,
            probe_kind="chat_completion",
            status="ok",
            is_available=True,
            response_preview=preview,
            error_type=None,
            error_code=None,
            error_message=None,
            http_status=200,
            metadata={"series": _model_series(model_name)},
            tested_at=tested_at,
        )
    except Exception as exc:
        error_type = type(exc).__name__
        http_status = getattr(exc, "status_code", None)
        error_code, error_message = _extract_error_details(exc)
        return LlmHealthRecord(
            provider_name=provider_name,
            base_url=OPENAI_BASE_URL,
            model_name=model_name,
            probe_kind="chat_completion",
            status="error",
            is_available=False,
            response_preview=None,
            error_type=error_type,
            error_code=error_code,
            error_message=error_message,
            http_status=http_status,
            metadata={"series": _model_series(model_name)},
            tested_at=tested_at,
        )


def _extract_error_details(exc: Exception) -> tuple[str | None, str | None]:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            return str(code) if code is not None else None, (
                str(message) if message is not None else str(exc)
            )
    return None, str(exc)


def _provider_name_from_base_url(base_url: str | None) -> str:
    if not base_url:
        return "openai-compatible"
    parsed = urlparse(base_url)
    host = parsed.netloc or parsed.path
    safe = host.replace(".", "-").strip("-")
    return safe or "openai-compatible"


def _model_series(model_name: str) -> str:
    if model_name.startswith("gpt-5"):
        return "gpt-5"
    if model_name.startswith("gpt-4"):
        return "gpt-4"
    return "other"


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
        raise RuntimeError(
            f"MySQL llm_health persistence failed: {completed.stderr.strip() or 'Unknown MySQL error.'}"
        )


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
