"""SQLite store for ETL snapshots, AST graph, and dead letters."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ast_parser import FunctionCallEdge, FunctionNode
from ..schemas import GitHubIssue, GitHubPullRequest, RepoMeta


class ETLStore:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def upsert_repo(self, repo: RepoMeta) -> None:
        self._execute(
            """
            INSERT INTO repos(repo_id, full_name, payload_json, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                full_name = excluded.full_name,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (repo.id, repo.full_name, repo.model_dump_json(), _now_iso()),
        )

    def upsert_issues(self, issues: list[GitHubIssue]) -> None:
        rows = [(i.id, i.repo, i.number, i.model_dump_json(), _now_iso()) for i in issues]
        self._executemany(
            """
            INSERT INTO issues(issue_id, repo, number, payload_json, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(issue_id) DO UPDATE SET
                repo = excluded.repo,
                number = excluded.number,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            rows,
        )

    def upsert_pulls(self, pulls: list[GitHubPullRequest]) -> None:
        rows = [(p.id, p.repo, p.number, p.model_dump_json(), _now_iso()) for p in pulls]
        self._executemany(
            """
            INSERT INTO pulls(pull_id, repo, number, payload_json, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(pull_id) DO UPDATE SET
                repo = excluded.repo,
                number = excluded.number,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            rows,
        )

    def replace_ast_snapshot(
        self,
        repo: str,
        commit_sha: str | None,
        function_nodes: list[FunctionNode],
        call_edges: list[FunctionCallEdge],
    ) -> None:
        conn = self._ensure_conn()
        now = _now_iso()
        conn.execute("DELETE FROM code_functions WHERE repo = ?", (repo,))
        conn.execute("DELETE FROM code_function_calls WHERE repo = ?", (repo,))

        if function_nodes:
            conn.executemany(
                """
                INSERT INTO code_functions(repo, commit_sha, function_name, language, file_path, start_line, end_line, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        repo,
                        commit_sha,
                        fn.name,
                        fn.language,
                        fn.file_path,
                        fn.start_line,
                        fn.end_line,
                        now,
                    )
                    for fn in function_nodes
                ],
            )

        if call_edges:
            conn.executemany(
                """
                INSERT INTO code_function_calls(repo, commit_sha, caller, callee, file_path, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                [(repo, commit_sha, e.caller, e.callee, e.file_path, now) for e in call_edges],
            )
        conn.commit()

    def add_dead_letter(
        self,
        task_type: str,
        payload: dict[str, Any],
        error_message: str,
        retry_count: int,
    ) -> None:
        self._execute(
            """
            INSERT INTO failed_tasks(task_type, payload_json, error_message, retry_count, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (task_type, json.dumps(payload, ensure_ascii=False), error_message, retry_count, _now_iso()),
        )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        conn = self._ensure_conn()
        conn.execute(sql, params)
        conn.commit()

    def _executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        conn = self._ensure_conn()
        conn.executemany(sql, rows)
        conn.commit()

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
            CREATE TABLE IF NOT EXISTS repos (
                repo_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                issue_id INTEGER PRIMARY KEY,
                repo TEXT NOT NULL,
                number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pulls (
                pull_id INTEGER PRIMARY KEY,
                repo TEXT NOT NULL,
                number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT NOT NULL,
                commit_sha TEXT,
                function_name TEXT NOT NULL,
                language TEXT NOT NULL,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_function_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT NOT NULL,
                commit_sha TEXT,
                caller TEXT NOT NULL,
                callee TEXT NOT NULL,
                file_path TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS failed_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                error_message TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('etl_store_schema_version', ?)",
            (str(self.SCHEMA_VERSION),),
        )
        conn.commit()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
