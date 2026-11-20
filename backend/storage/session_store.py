"""SQLite-backed cache index and presentation-session event log."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedAnalysis:
    """Serialized analysis response plus its project-local evidence directory."""

    response_json: str
    evidence_dir: str


class LocalSessionStore:
    """Use short-lived SQLite connections for safe local API persistence."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    cache_key TEXT PRIMARY KEY,
                    modality TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    model_identity TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    evidence_dir TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS session_events (
                    id TEXT PRIMARY KEY,
                    modality TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    cached INTEGER NOT NULL CHECK (cached IN (0, 1)),
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS session_events_created_at_idx
                    ON session_events(created_at DESC);
                """
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()

    def get_analysis(self, cache_key: str) -> CachedAnalysis | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT response_json, evidence_dir
                FROM analysis_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return CachedAnalysis(
            response_json=str(row["response_json"]),
            evidence_dir=str(row["evidence_dir"]),
        )

    def record_cache_hit(self, cache_key: str) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE analysis_cache
                SET last_accessed_at = ?, hit_count = hit_count + 1
                WHERE cache_key = ?
                """,
                (now, cache_key),
            )
            connection.commit()

    def put_analysis(
        self,
        *,
        cache_key: str,
        modality: str,
        input_digest: str,
        model_identity: str,
        response_json: str,
        evidence_dir: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO analysis_cache (
                    cache_key, modality, input_digest, model_identity,
                    response_json, evidence_dir, created_at, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    modality = excluded.modality,
                    input_digest = excluded.input_digest,
                    model_identity = excluded.model_identity,
                    response_json = excluded.response_json,
                    evidence_dir = excluded.evidence_dir,
                    last_accessed_at = excluded.last_accessed_at
                """,
                (
                    cache_key,
                    modality,
                    input_digest,
                    model_identity,
                    response_json,
                    evidence_dir,
                    now,
                    now,
                ),
            )
            connection.commit()

    def delete_analysis(self, cache_key: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM analysis_cache WHERE cache_key = ?",
                (cache_key,),
            )
            connection.commit()

    def cache_count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM analysis_cache"
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def record_session_event(self, payload: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO session_events (
                    id, modality, source_name, decision, cached,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload["id"]),
                    str(payload["modality"]),
                    str(payload["source"]),
                    str(payload["decision"]),
                    int(bool(payload["cached"])),
                    json.dumps(payload, separators=(",", ":")),
                    str(payload["created_at"]),
                ),
            )
            connection.commit()

    def list_session_events(self, *, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM session_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [json.loads(str(row["payload_json"])) for row in rows]

    def event_count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM session_events"
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def clear_session_events(self) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM session_events")
            connection.commit()
            return max(cursor.rowcount, 0)
