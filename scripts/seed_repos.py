"""Pull seed repository metadata + issues + PRs + AST into local SQLite cache.

Usage::

    python scripts/seed_repos.py --config configs/seed.yaml
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.etl.ast_parser import is_supported_file, parse_file
from backend.app.etl.github import GitHubClient
from backend.app.etl.logging_utils import configure_etl_logging, get_etl_logger
from backend.app.etl.store import ETLStore
from backend.app.config import get_settings

logger = get_etl_logger("seed_repos")


@dataclass(slots=True)
class LocalCodeRoot:
    repo: str
    path: str


@dataclass(slots=True)
class SeedConfig:
    repos: list[str]
    db_path: str = "data/cache.db"
    issue_state: str = "all"
    pull_state: str = "closed"
    per_page: int = 100
    max_retries: int = 3
    retry_base_seconds: float = 0.5
    local_code_roots: list[LocalCodeRoot] = field(default_factory=list)


def load_seed_config(path: str | Path | None) -> SeedConfig:
    settings = get_settings()
    config_path = Path(path) if path else None
    if config_path is None or not config_path.exists():
        return SeedConfig(repos=settings.seed_repo_list, db_path=settings.etl_cache_db_path)

    raw = _load_yaml(config_path)
    local_roots = [
        LocalCodeRoot(repo=str(item["repo"]), path=str(item["path"]))
        for item in raw.get("local_code_roots", [])
        if isinstance(item, dict) and "repo" in item and "path" in item
    ]
    return SeedConfig(
        repos=[str(r) for r in raw.get("repos", settings.seed_repo_list)],
        db_path=str(raw.get("db_path", settings.etl_cache_db_path)),
        issue_state=str(raw.get("issue_state", "all")),
        pull_state=str(raw.get("pull_state", "closed")),
        per_page=int(raw.get("per_page", 100)),
        max_retries=int(raw.get("max_retries", 3)),
        retry_base_seconds=float(raw.get("retry_base_seconds", 0.5)),
        local_code_roots=local_roots,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError("PyYAML is required for --config YAML files. Install `pyyaml`.") from exc

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected top-level mapping in {path}")
    return loaded


async def run(config: SeedConfig) -> dict[str, Any]:
    store = ETLStore(config.db_path)
    summary: dict[str, Any] = {"repos_total": len(config.repos), "repos_success": 0, "repos_failed": 0}
    logger.info("seed_start", repos=config.repos, db_path=config.db_path)

    try:
        async with GitHubClient(max_retries=config.max_retries) as client:
            for repo in config.repos:
                ok = await _ingest_repo_with_retries(repo=repo, client=client, store=store, config=config)
                if ok:
                    summary["repos_success"] += 1
                else:
                    summary["repos_failed"] += 1

        for local_root in config.local_code_roots:
            parsed = _ingest_local_code(local_root, store)
            logger.info(
                "seed_local_code_done",
                repo=local_root.repo,
                path=local_root.path,
                functions=parsed["functions"],
                calls=parsed["calls"],
            )
    finally:
        store.close()

    logger.info("seed_done", **summary)
    return summary


async def _ingest_repo_with_retries(
    *,
    repo: str,
    client: GitHubClient,
    store: ETLStore,
    config: SeedConfig,
) -> bool:
    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            await _ingest_repo_once(repo=repo, client=client, store=store, config=config)
            logger.info("seed_repo_ok", repo=repo, attempt=attempt)
            return True
        except Exception as exc:  # pragma: no cover - defensive path
            last_error = exc
            logger.warning("seed_repo_retry", repo=repo, attempt=attempt, error=str(exc))
            if attempt < config.max_retries:
                await asyncio.sleep(min(config.retry_base_seconds * (2 ** (attempt - 1)), 8))

    store.add_dead_letter(
        task_type="seed_repo",
        payload={"repo": repo},
        error_message=str(last_error) if last_error else "unknown error",
        retry_count=config.max_retries,
    )
    logger.error("seed_repo_dead_letter", repo=repo, retries=config.max_retries)
    return False


async def _ingest_repo_once(
    *,
    repo: str,
    client: GitHubClient,
    store: ETLStore,
    config: SeedConfig,
) -> None:
    logger.info("seed_repo_start", repo=repo)
    repo_meta = await client.get_repo(repo)
    issues = await client.list_issues(repo, state=config.issue_state, per_page=config.per_page)
    pulls = await client.list_pulls(repo, state=config.pull_state, per_page=config.per_page)

    store.upsert_repo(repo_meta)
    store.upsert_issues(issues)
    store.upsert_pulls(pulls)
    logger.info("seed_repo_ingested", repo=repo, issues=len(issues), pulls=len(pulls))


def _ingest_local_code(local_root: LocalCodeRoot, store: ETLStore) -> dict[str, int]:
    root = Path(local_root.path)
    if not root.exists():
        raise FileNotFoundError(f"local code root not found: {root}")

    all_functions = []
    all_calls = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not is_supported_file(path):
            continue
        try:
            function_nodes, call_edges = parse_file(path)
        except Exception as exc:  # pragma: no cover - malformed files should not stop job
            logger.warning("ast_parse_failed", file=str(path), error=str(exc))
            continue
        all_functions.extend(function_nodes)
        all_calls.extend(call_edges)

    store.replace_ast_snapshot(
        repo=local_root.repo,
        commit_sha=_resolve_commit_sha(root),
        function_nodes=all_functions,
        call_edges=all_calls,
    )
    return {"functions": len(all_functions), "calls": len(all_calls)}


def _resolve_commit_sha(path: Path) -> str | None:
    command = ["git", "rev-parse", "HEAD"]
    try:
        result = subprocess.run(command, cwd=path, check=False, capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def parse_args() -> Path | None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed GitHub data and local AST snapshots.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/seed.yaml"),
        help="Path to YAML config file. Falls back to env settings when missing.",
    )
    args = parser.parse_args()
    return args.config


async def main() -> None:
    configure_etl_logging()
    config_path = parse_args()
    config = load_seed_config(config_path)
    await run(config)


if __name__ == "__main__":
    asyncio.run(main())
