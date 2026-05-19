"""Named Cypher query helpers for common KG lookups."""

from __future__ import annotations

from typing import Any

from .client import Neo4jClient


class KGQueries:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def issue_adjacent_modules(
        self, repo: str, issue_number: int
    ) -> list[dict[str, Any]]:
        """Return modules directly affected by a given issue."""
        cypher = """
MATCH (i:Issue {repo: $repo, number: $issue_number})-[:AFFECTS]->(m:Module)
RETURN m.repo AS repo, m.path AS module_path, m.type AS module_type
ORDER BY module_path
"""
        return await self._client.run(cypher, repo=repo, issue_number=issue_number)

    async def pr_impact_scope(
        self, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """Return function-level impact scope for a PR."""
        cypher = """
MATCH (p:PR {repo: $repo, number: $pr_number})-[:MODIFIES]->(f:Function)
RETURN f.module_path AS module_path, f.name AS function_name, f.signature AS signature
ORDER BY module_path, function_name
"""
        return await self._client.run(cypher, repo=repo, pr_number=pr_number)

    async def repo_top_modules(self, repo: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return repo modules ranked by issue count."""
        cypher = """
MATCH (i:Issue {repo: $repo})-[:AFFECTS]->(m:Module {repo: $repo})
RETURN m.path AS module_path, count(i) AS issue_count
ORDER BY issue_count DESC, module_path
LIMIT $limit
"""
        return await self._client.run(cypher, repo=repo, limit=limit)

    async def issue_required_skills(
        self, repo: str, issue_number: int
    ) -> list[dict[str, Any]]:
        """Return skills required by a given issue."""
        cypher = """
MATCH (i:Issue {repo: $repo, number: $issue_number})-[:REQUIRES]->(s:Skill)
RETURN s.name AS skill, s.family AS family
ORDER BY skill
"""
        return await self._client.run(cypher, repo=repo, issue_number=issue_number)

    async def contributor_recent_prs(
        self, login: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return recently authored PRs by contributor."""
        cypher = """
MATCH (c:Contributor {login: $login})-[:AUTHORED]->(p:PR)
RETURN p.repo AS repo, p.number AS pr_number, p.title AS title, p.updated_at AS updated_at
ORDER BY updated_at DESC
LIMIT $limit
"""
        return await self._client.run(cypher, login=login, limit=limit)

    async def function_call_neighbors(
        self,
        repo: str,
        module_path: str,
        function_name: str,
        hops: int = 1,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return call-neighbor functions within bounded hop distance."""
        cypher = """
MATCH (f:Function {repo: $repo, module_path: $module_path, name: $function_name})
MATCH p=(f)-[:CALLS*1..$hops]->(n:Function)
RETURN DISTINCT n.module_path AS module_path, n.name AS function_name, length(p) AS hops
ORDER BY hops, module_path, function_name
LIMIT $limit
"""
        return await self._client.run(
            cypher,
            repo=repo,
            module_path=module_path,
            function_name=function_name,
            hops=max(1, hops),
            limit=limit,
        )
