"""Pull seed repository metadata + issues + PRs into Neo4j and Milvus.

Usage::

    python -m scripts.seed_repos
"""

from __future__ import annotations

import asyncio

from backend.app.config import get_settings


async def main() -> None:
    s = get_settings()
    print(f"[seed_repos] would ingest {len(s.seed_repo_list)} repos: {s.seed_repo_list}")
    print("[seed_repos] Implementation slated for Week 1 (member D).")


if __name__ == "__main__":
    asyncio.run(main())
