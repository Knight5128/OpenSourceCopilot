from __future__ import annotations

import asyncio

from backend.app.kg.queries import KGQueries


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return [{"ok": True, **params}]


def test_named_queries_send_expected_params() -> None:
    async def run() -> None:
        client = _FakeClient()
        queries = KGQueries(client)  # type: ignore[arg-type]

        await queries.issue_adjacent_modules("owner/repo", 12)
        await queries.pr_impact_scope("owner/repo", 34)
        await queries.repo_top_modules("owner/repo", limit=5)
        await queries.issue_required_skills("owner/repo", 56)
        await queries.contributor_recent_prs("alice", limit=7)
        await queries.function_call_neighbors("owner/repo", "a.py", "foo", hops=2, limit=9)

        assert len(client.calls) == 6
        assert client.calls[0][1] == {"repo": "owner/repo", "issue_number": 12}
        assert client.calls[1][1] == {"repo": "owner/repo", "pr_number": 34}
        assert client.calls[2][1] == {"repo": "owner/repo", "limit": 5}
        assert client.calls[3][1] == {"repo": "owner/repo", "issue_number": 56}
        assert client.calls[4][1] == {"login": "alice", "limit": 7}
        assert client.calls[5][1] == {
            "repo": "owner/repo",
            "module_path": "a.py",
            "function_name": "foo",
            "hops": 2,
            "limit": 9,
        }

    asyncio.run(run())
