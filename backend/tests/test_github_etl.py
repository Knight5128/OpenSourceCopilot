"""Tests for the GitHub ETL client."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import httpx

from backend.app.etl.cache import SQLiteHTTPCache
from backend.app.etl.github import GitHubClient


def _repo_payload() -> dict:
    return {
        "id": 1,
        "full_name": "owner/repo",
        "name": "repo",
        "owner": {"login": "owner"},
        "description": "demo repo",
        "html_url": "https://github.com/owner/repo",
        "stargazers_count": 42,
        "forks_count": 3,
        "open_issues_count": 7,
        "language": "Python",
        "topics": ["ai", "rag"],
        "license": {"spdx_id": "MIT"},
        "default_branch": "main",
        "pushed_at": "2026-05-18T12:00:00Z",
        "updated_at": "2026-05-19T12:00:00Z",
    }


def _issue_payload(number: int, *, pull_request: bool = False) -> dict:
    payload = {
        "id": number,
        "number": number,
        "title": f"Issue {number}",
        "body": "body",
        "state": "open",
        "labels": [{"name": "good first issue"}],
        "user": {"login": "alice"},
        "author_association": "CONTRIBUTOR",
        "comments": 2,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "created_at": "2026-05-18T12:00:00Z",
        "updated_at": "2026-05-19T12:00:00Z",
        "closed_at": None,
    }
    if pull_request:
        payload["pull_request"] = {"url": "https://api.github.com/pulls/2"}
    return payload


def _pull_payload(number: int, *, updated_at: str) -> dict:
    return {
        "id": number,
        "number": number,
        "title": f"PR {number}",
        "body": "body",
        "state": "closed",
        "merged_at": "2026-05-19T12:00:00Z",
        "user": {"login": "bob"},
        "author_association": "FIRST_TIMER",
        "comments": 1,
        "commits": 2,
        "additions": 10,
        "deletions": 4,
        "changed_files": 3,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "created_at": "2026-05-18T12:00:00Z",
        "updated_at": updated_at,
        "closed_at": "2026-05-19T12:00:00Z",
    }


def test_get_repo_normalises_metadata() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json=_repo_payload())
        )
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GitHubClient(client=http_client)
            repo = await client.get_repo("owner/repo")

        assert repo.full_name == "owner/repo"
        assert repo.owner == "owner"
        assert repo.stars == 42
        assert repo.primary_language == "Python"
        assert repo.topics == ["ai", "rag"]
        assert repo.license_spdx == "MIT"

    asyncio.run(run())


def test_rate_limit_rotates_to_next_token() -> None:
    async def run() -> None:
        seen_auth: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            auth = request.headers.get("Authorization")
            seen_auth.append(auth)
            if auth == "Bearer exhausted":
                return httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={})
            return httpx.Response(200, json=_repo_payload())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GitHubClient(tokens=["exhausted", "backup"], client=http_client)
            repo = await client.get_repo("owner/repo")

        assert repo.full_name == "owner/repo"
        assert seen_auth == ["Bearer exhausted", "Bearer backup"]

    asyncio.run(run())


def test_list_issues_paginates_filters_pull_requests_and_sends_since() -> None:
    async def run() -> None:
        seen_since: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            seen_since.append(params.get("since"))
            if params["page"] == "1":
                return httpx.Response(
                    200,
                    json=[
                        _issue_payload(1),
                        _issue_payload(2, pull_request=True),
                    ],
                )
            return httpx.Response(200, json=[_issue_payload(3)])

        transport = httpx.MockTransport(handler)
        since = datetime(2026, 5, 19, tzinfo=timezone.utc)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GitHubClient(client=http_client)
            issues = await client.list_issues("owner/repo", since=since, per_page=2)

        assert [issue.number for issue in issues] == [1, 3]
        assert issues[0].labels == ["good first issue"]
        assert all(value == "2026-05-19T00:00:00+00:00" for value in seen_since)

    asyncio.run(run())


def test_list_pulls_filters_since_locally() -> None:
    async def run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    _pull_payload(1, updated_at="2026-05-17T12:00:00Z"),
                    _pull_payload(2, updated_at="2026-05-19T12:00:00Z"),
                ],
            )

        transport = httpx.MockTransport(handler)
        since = datetime(2026, 5, 18, tzinfo=timezone.utc)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GitHubClient(client=http_client)
            pulls = await client.list_pulls("owner/repo", since=since)

        assert [pull.number for pull in pulls] == [2]
        assert pulls[0].changed_files == 3

    asyncio.run(run())


def test_sqlite_cache_hits_on_second_call(tmp_path) -> None:
    async def run() -> None:
        calls = 0
        cache = SQLiteHTTPCache(tmp_path / "cache.db", ttl_seconds=600)

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_repo_payload())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GitHubClient(client=http_client, cache=cache)
            first = await client.get_repo("owner/repo")
            second = await client.get_repo("owner/repo")
            await client.aclose()

        assert calls == 1
        assert first.id == second.id

        conn = sqlite3.connect(tmp_path / "cache.db")
        try:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == str(SQLiteHTTPCache.SCHEMA_VERSION)

    asyncio.run(run())
