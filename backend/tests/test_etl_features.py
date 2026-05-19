from __future__ import annotations

import asyncio
import importlib.util
import sqlite3

import pytest

from backend.app.etl.ast_parser import parse_code
from backend.app.etl.store import ETLStore
from scripts.seed_repos import SeedConfig, _ingest_repo_with_retries

TREE_SITTER_READY = (
    importlib.util.find_spec("tree_sitter") is not None
    and importlib.util.find_spec("tree_sitter_languages") is not None
)


@pytest.mark.skipif(not TREE_SITTER_READY, reason="tree-sitter dependencies are not installed")
def test_parse_python_functions_and_calls() -> None:
    code = """
def helper():
    return 1

def main():
    helper()
"""
    functions, edges = parse_code(code, language="python", file_path="demo.py")
    assert {f.name for f in functions} == {"helper", "main"}
    assert {(e.caller, e.callee) for e in edges} == {("main", "helper")}


@pytest.mark.skipif(not TREE_SITTER_READY, reason="tree-sitter dependencies are not installed")
def test_parse_typescript_functions_and_calls() -> None:
    code = """
function helper() {
  return 1;
}
const run = () => {
  helper();
};
"""
    functions, edges = parse_code(code, language="typescript", file_path="demo.ts")
    assert {f.name for f in functions} == {"helper", "run"}
    assert {(e.caller, e.callee) for e in edges} == {("run", "helper")}


def test_etl_store_persists_ast_and_dead_letter(tmp_path) -> None:
    if not TREE_SITTER_READY:
        pytest.skip("tree-sitter dependencies are not installed")
    db_path = tmp_path / "etl.db"
    store = ETLStore(db_path)
    try:
        functions, edges = parse_code(
            "def a():\n    b()\n\ndef b():\n    return 1\n",
            language="python",
            file_path="x.py",
        )
        store.replace_ast_snapshot("demo/repo", None, functions, edges)
        store.add_dead_letter("seed_repo", {"repo": "demo/repo"}, "boom", 3)
    finally:
        store.close()

    conn = sqlite3.connect(db_path)
    try:
        fn_count = conn.execute("SELECT COUNT(*) FROM code_functions").fetchone()[0]
        call_count = conn.execute("SELECT COUNT(*) FROM code_function_calls").fetchone()[0]
        dl_count = conn.execute("SELECT COUNT(*) FROM failed_tasks").fetchone()[0]
    finally:
        conn.close()
    assert fn_count == 2
    assert call_count == 1
    assert dl_count == 1


def test_failed_seed_repo_written_to_dead_letter(tmp_path) -> None:
    class FakeClient:
        async def get_repo(self, _repo: str):
            raise RuntimeError("upstream unavailable")

        async def list_issues(self, _repo: str, **_kwargs):
            return []

        async def list_pulls(self, _repo: str, **_kwargs):
            return []

    async def run() -> None:
        store = ETLStore(tmp_path / "seed.db")
        try:
            config = SeedConfig(repos=["owner/repo"], db_path=str(tmp_path / "seed.db"), max_retries=2)
            ok = await _ingest_repo_with_retries(
                repo="owner/repo",
                client=FakeClient(),  # type: ignore[arg-type]
                store=store,
                config=config,
            )
            assert not ok
        finally:
            store.close()

    asyncio.run(run())

    conn = sqlite3.connect(tmp_path / "seed.db")
    try:
        row = conn.execute(
            "SELECT task_type, retry_count FROM failed_tasks ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("seed_repo", 2)
