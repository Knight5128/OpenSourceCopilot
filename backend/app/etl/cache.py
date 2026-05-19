"""SQLite-backed cache for GitHub ETL HTTP responses."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any


class SQLiteHTTPCache:
    """Small persistent cache keyed by `(method, path, params)`."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path, *, ttl_seconds: int = 86_400) -> None:
        self._db_path = Path(db_path)
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._conn: sqlite3.Connection | None = None

    def get(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any | None:
        cache_key = _make_cache_key(method, path, params)
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(
                """
                SELECT response_json, expires_at
                FROM http_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
            if row is None:
                return None

            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at <= datetime.now(UTC):
                conn.execute("DELETE FROM http_cache WHERE cache_key = ?", (cache_key,))
                conn.commit()
                return None

            return json.loads(row["response_json"])

    def set(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        payload: Any,
    ) -> None:
        cache_key = _make_cache_key(method, path, params)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._ttl_seconds)

        with self._lock:
            conn = self._ensure_conn()
            conn.execute(
                """
                INSERT INTO http_cache(cache_key, method, path, params_json, response_json, expires_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key)
                DO UPDATE SET
                    response_json = excluded.response_json,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    cache_key,
                    method.upper(),
                    path,
                    json.dumps(_normalise_params(params), sort_keys=True),
                    json.dumps(payload),
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def aclose(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn
            self._migrate(conn)
        return self._conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS http_cache (
                cache_key TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                params_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(self.SCHEMA_VERSION),),
        )
        conn.commit()


def _make_cache_key(method: str, path: str, params: dict[str, Any] | None) -> str:
    serialised = json.dumps(_normalise_params(params), sort_keys=True, separators=(",", ":"))
    return f"{method.upper()}:{path}:{serialised}"


def _normalise_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    normalised: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, datetime):
            normalised[key] = value.isoformat()
            continue
        normalised[key] = value
    return normalised
