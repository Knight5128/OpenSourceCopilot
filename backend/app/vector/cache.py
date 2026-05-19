"""SQLite cache for deterministic embedding reuse."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock


class SQLiteEmbeddingCache:
    """Persistent cache keyed by `(space, model, sha256(text))`."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = Lock()
        self._conn: sqlite3.Connection | None = None
        self._hits = 0
        self._misses = 0

    def get(self, space: str, model: str, text: str) -> list[float] | None:
        cache_key = make_embedding_key(space, model, text)
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(
                "SELECT vector_json FROM embedding_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                self._misses += 1
                return None

            self._hits += 1
            conn.execute(
                """
                UPDATE embedding_cache
                SET hit_count = hit_count + 1, last_accessed_at = ?
                WHERE cache_key = ?
                """,
                (datetime.now(UTC).isoformat(), cache_key),
            )
            conn.commit()
            return json.loads(row["vector_json"])

    def get_many(self, space: str, model: str, texts: list[str]) -> list[list[float] | None]:
        return [self.get(space, model, text) for text in texts]

    def set(self, space: str, model: str, text: str, vector: list[float]) -> None:
        cache_key = make_embedding_key(space, model, text)
        text_hash = make_text_hash(text)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            conn = self._ensure_conn()
            conn.execute(
                """
                INSERT INTO embedding_cache(
                    cache_key, text_hash, space, model, vector_json, dim, hit_count,
                    created_at, last_accessed_at
                )
                VALUES(?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(cache_key)
                DO UPDATE SET
                    vector_json = excluded.vector_json,
                    dim = excluded.dim,
                    last_accessed_at = excluded.last_accessed_at
                """,
                (
                    cache_key,
                    text_hash,
                    space,
                    model,
                    json.dumps(vector, separators=(",", ":")),
                    len(vector),
                    now,
                    now,
                ),
            )
            conn.commit()

    def set_many(self, space: str, model: str, items: list[tuple[str, list[float]]]) -> None:
        for text, vector in items:
            self.set(space, model, text, vector)

    def stats(self) -> dict[str, float | int]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        return {"hits": self._hits, "misses": self._misses, "hit_rate": hit_rate, "rows": rows}

    def close(self) -> None:
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
            CREATE TABLE IF NOT EXISTS embedding_cache (
                cache_key TEXT PRIMARY KEY,
                text_hash TEXT NOT NULL,
                space TEXT NOT NULL,
                model TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                dim INTEGER NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_accessed_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embedding_cache_lookup
            ON embedding_cache(space, model, text_hash)
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(self.SCHEMA_VERSION),),
        )
        conn.commit()


def make_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_embedding_key(space: str, model: str, text: str) -> str:
    return f"{space}:{model}:{make_text_hash(text)}"
