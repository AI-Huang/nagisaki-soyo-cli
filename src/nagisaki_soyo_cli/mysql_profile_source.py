from __future__ import annotations

import binascii
import os
import subprocess
from dataclasses import dataclass

from .config import MYSQL_BIN, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from .profile_analysis import TextSample


@dataclass
class MysqlProfileSource:
    user_id: str
    user_name: str
    matched_author_name: str | None
    samples: list[TextSample]


def load_mysql_profile_source(
    *,
    user_name: str | None,
    user_id: str | None,
    max_notes: int = 50,
    max_comments: int = 50,
) -> MysqlProfileSource:
    if not MYSQL_USER:
        raise RuntimeError("MYSQL_USER is required for MySQL-backed profile analysis.")

    user_record = _load_user_record(user_name=user_name, user_id=user_id)
    resolved_user_id = user_record["user_id"]
    resolved_user_name = user_record["user_name"]
    matched_author_name = user_record["matched_author_name"]

    samples: list[TextSample] = []
    bio = user_record["bio"]
    if bio:
        samples.append(TextSample(text=bio, source="mysql-user-bio", created_at=user_record["crawled_at"]))

    samples.extend(_load_note_samples(resolved_user_id, max_notes=max_notes))
    samples.extend(_load_comment_samples(resolved_user_name, matched_author_name, max_comments=max_comments))

    if not samples:
        raise RuntimeError("No text samples were found for the requested MySQL user.")

    return MysqlProfileSource(
        user_id=resolved_user_id,
        user_name=resolved_user_name,
        matched_author_name=matched_author_name,
        samples=samples,
    )


def _load_user_record(*, user_name: str | None, user_id: str | None) -> dict[str, str]:
    where_clauses: list[str] = []
    if user_id:
        where_clauses.append(f"u.user_id = {_sql_quote(user_id)}")
    if user_name:
        quoted_name = _sql_quote(user_name)
        where_clauses.append(f"(u.nickname = {quoted_name} OR a.author_name = {quoted_name})")
    if not where_clauses:
        raise RuntimeError("Either user_name or user_id is required.")

    query = f"""
SELECT
    HEX(u.user_id),
    HEX(COALESCE(NULLIF(u.nickname, ''), a.author_name, u.user_id)),
    HEX(COALESCE(a.author_name, '')),
    HEX(COALESCE(u.bio, '')),
    HEX(CAST(u.crawled_at AS CHAR))
FROM users AS u
LEFT JOIN authors AS a ON a.author_id = u.user_id
WHERE {" OR ".join(where_clauses)}
LIMIT 1
"""
    rows = _run_mysql_tsv(query, expected_columns=5)
    if not rows:
        raise RuntimeError("No matching user was found in xhs_crawler.")
    row = rows[0]
    return {
        "user_id": _decode_hex(row[0]),
        "user_name": _decode_hex(row[1]),
        "matched_author_name": _decode_hex(row[2]),
        "bio": _decode_hex(row[3]),
        "crawled_at": _decode_hex(row[4]),
    }


def _load_note_samples(user_id: str, *, max_notes: int) -> list[TextSample]:
    query = f"""
SELECT
    HEX(n.note_id),
    HEX(COALESCE(n.title, '')) AS title,
    HEX(COALESCE(n.`desc`, '')) AS note_desc,
    HEX(COALESCE(n.publish_time, '')) AS publish_time,
    HEX(COALESCE(GROUP_CONCAT(t.tag ORDER BY t.tag SEPARATOR ' '), '')) AS tags
FROM notes AS n
LEFT JOIN tags AS t ON t.note_id = n.note_id
WHERE n.author_id = {_sql_quote(user_id)}
GROUP BY n.note_id, n.title, n.`desc`, n.publish_time, n.crawled_at
ORDER BY n.crawled_at DESC
LIMIT {max_notes}
"""
    rows = _run_mysql_tsv(query, expected_columns=5)
    samples: list[TextSample] = []
    for note_id_hex, title_hex, note_desc_hex, publish_time_hex, tags_hex in rows:
        note_id = _decode_hex(note_id_hex)
        title = _decode_hex(title_hex)
        note_desc = _decode_hex(note_desc_hex)
        publish_time = _decode_hex(publish_time_hex)
        tags = _decode_hex(tags_hex)
        note_text_parts = [part for part in (title, note_desc) if part]
        if note_text_parts:
            samples.append(
                TextSample(
                    text="\n".join(note_text_parts),
                    source="mysql-note",
                    created_at=publish_time or None,
                )
            )
        if tags:
            samples.append(
                TextSample(
                    text=tags,
                    source="mysql-note-tags",
                    created_at=publish_time or None,
                )
            )
        if not note_text_parts and not tags:
            samples.append(TextSample(text=note_id, source="mysql-note-id", created_at=publish_time or None))
    return samples


def _load_comment_samples(user_name: str, matched_author_name: str | None, *, max_comments: int) -> list[TextSample]:
    names = [name for name in {user_name, matched_author_name or ""} if name]
    if not names:
        return []
    in_list = ", ".join(_sql_quote(name) for name in names)
    query = f"""
SELECT
    HEX(COALESCE(c.content, '')) AS content,
    HEX(CAST(c.crawled_at AS CHAR)) AS crawled_at
FROM comments AS c
WHERE c.author_name IN ({in_list})
ORDER BY c.crawled_at DESC
LIMIT {max_comments}
"""
    rows = _run_mysql_tsv(query, expected_columns=2)
    samples: list[TextSample] = []
    for content_hex, crawled_at_hex in rows:
        content = _decode_hex(content_hex)
        crawled_at = _decode_hex(crawled_at_hex)
        if content:
            samples.append(TextSample(text=content, source="mysql-comment", created_at=crawled_at or None))
    return samples


def _run_mysql_tsv(query: str, *, expected_columns: int) -> list[list[str]]:
    command = [
        MYSQL_BIN,
        "--protocol=TCP",
        f"-h{MYSQL_HOST}",
        f"-P{MYSQL_PORT}",
        f"-u{MYSQL_USER}",
        "--batch",
        "--raw",
        "--skip-column-names",
        "-D",
        MYSQL_DATABASE,
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
        stderr = completed.stderr.strip() or "Unknown MySQL error."
        raise RuntimeError(f"MySQL query failed: {stderr}")
    rows: list[list[str]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        columns = line.split("\t")
        if len(columns) != expected_columns:
            raise RuntimeError(f"Unexpected MySQL result shape. Expected {expected_columns} columns, got {len(columns)}.")
        rows.append(columns)
    return rows


def _sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _decode_hex(value: str) -> str:
    if not value:
        return ""
    try:
        return binascii.unhexlify(value).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise RuntimeError("Failed to decode MySQL HEX result.") from exc
