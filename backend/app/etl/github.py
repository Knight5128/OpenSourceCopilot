"""Async GitHub REST client used by the ETL pipeline.

The client keeps GitHub-specific behaviour in one place: token rotation, basic
rate-limit handling, pagination, and normalisation into project schemas.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ..config import get_settings
from ..schemas import GitHubIssue, GitHubPullRequest, RepoMeta


class GitHubClient:
    """Small async wrapper around GitHub's REST API.

    Parameters are intentionally injectable so tests can use `httpx.MockTransport`
    without real network calls.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        tokens: Sequence[str] | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        settings = get_settings()
        configured_tokens = list(tokens or [])
        if token:
            configured_tokens.insert(0, token)
        elif settings.github_token:
            configured_tokens.insert(0, settings.github_token)

        self.tokens = [t for t in configured_tokens if t]
        self._token_index = 0
        self.base = (base_url or settings.github_api_base).rstrip("/")
        self.max_retries = max_retries

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    @property
    def token(self) -> str | None:
        if not self.tokens:
            return None
        return self.tokens[self._token_index]

    async def _get(self, path: str, **params: Any) -> Any:
        resp = await self._request("GET", path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base}{path}"
        attempts = 0
        token_rotations = 0

        while True:
            headers = self._headers()
            resp = await self._client.request(method, url, headers=headers, **kwargs)

            if self._is_rate_limited(resp):
                if self._rotate_token():
                    token_rotations += 1
                    if token_rotations < max(1, len(self.tokens)):
                        continue

                attempts += 1
                if attempts >= self.max_retries:
                    resp.raise_for_status()
                await self._sleep_for_rate_limit(resp, attempts)
                continue

            if resp.status_code in {500, 502, 503, 504} and attempts < self.max_retries - 1:
                attempts += 1
                await asyncio.sleep(min(2**attempts, 10))
                continue

            return resp

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _rotate_token(self) -> bool:
        if len(self.tokens) <= 1:
            return False
        self._token_index = (self._token_index + 1) % len(self.tokens)
        return True

    @staticmethod
    def _is_rate_limited(resp: httpx.Response) -> bool:
        if resp.status_code == 429:
            return True
        if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
            return True
        return False

    @staticmethod
    async def _sleep_for_rate_limit(resp: httpx.Response, attempt: int) -> None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            await asyncio.sleep(min(int(retry_after), 60))
            return

        reset = resp.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            delay = max(0.0, (reset_at - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(min(delay, 60))
            return

        await asyncio.sleep(min(2**attempt, 10))

    async def _paginate(self, path: str, **params: Any) -> list[dict[str, Any]]:
        page = 1
        per_page = int(params.pop("per_page", 100))
        collected: list[dict[str, Any]] = []

        while True:
            data = await self._get(path, per_page=per_page, page=page, **params)
            if not isinstance(data, list):
                raise TypeError(f"Expected GitHub list response for {path}, got {type(data)!r}")

            collected.extend(data)
            if len(data) < per_page:
                return collected

            page += 1

    async def get_repo(self, full_name: str) -> RepoMeta:
        data = await self._get(f"/repos/{full_name}")
        return self._parse_repo(data)

    async def list_issues(
        self,
        full_name: str,
        *,
        state: str = "all",
        since: datetime | None = None,
        per_page: int = 100,
    ) -> list[GitHubIssue]:
        params: dict[str, Any] = {"state": state, "per_page": per_page}
        if since:
            params["since"] = since.isoformat()

        data = await self._paginate(
            f"/repos/{full_name}/issues",
            **params,
        )
        return [self._parse_issue(full_name, item) for item in data if "pull_request" not in item]

    async def list_pulls(
        self,
        full_name: str,
        *,
        state: str = "closed",
        since: datetime | None = None,
        per_page: int = 100,
    ) -> list[GitHubPullRequest]:
        params: dict[str, Any] = {"state": state, "per_page": per_page}

        data = await self._paginate(
            f"/repos/{full_name}/pulls",
            **params,
        )
        pulls = [self._parse_pull(full_name, item) for item in data]
        if since is None:
            return pulls
        return [pull for pull in pulls if pull.updated_at >= since]

    @staticmethod
    def _parse_repo(data: dict[str, Any]) -> RepoMeta:
        owner = data.get("owner") or {}
        license_info = data.get("license") or {}
        return RepoMeta(
            id=data["id"],
            full_name=data["full_name"],
            name=data["name"],
            owner=owner.get("login", ""),
            description=data.get("description"),
            html_url=data["html_url"],
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            open_issues=data.get("open_issues_count", 0),
            primary_language=data.get("language"),
            topics=data.get("topics") or [],
            license_spdx=license_info.get("spdx_id"),
            default_branch=data.get("default_branch", "main"),
            pushed_at=_parse_datetime(data.get("pushed_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )

    @staticmethod
    def _parse_issue(repo: str, data: dict[str, Any]) -> GitHubIssue:
        user = data.get("user") or {}
        return GitHubIssue(
            id=data["id"],
            repo=repo,
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[label["name"] for label in data.get("labels", []) if "name" in label],
            author_login=user.get("login"),
            author_association=data.get("author_association"),
            comments=data.get("comments", 0),
            html_url=data["html_url"],
            created_at=_parse_datetime(data["created_at"]),
            updated_at=_parse_datetime(data["updated_at"]),
            closed_at=_parse_datetime(data.get("closed_at")),
        )

    @staticmethod
    def _parse_pull(repo: str, data: dict[str, Any]) -> GitHubPullRequest:
        user = data.get("user") or {}
        return GitHubPullRequest(
            id=data["id"],
            repo=repo,
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            merged_at=_parse_datetime(data.get("merged_at")),
            author_login=user.get("login"),
            author_association=data.get("author_association"),
            comments=data.get("comments", 0),
            commits=data.get("commits", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            html_url=data["html_url"],
            created_at=_parse_datetime(data["created_at"]),
            updated_at=_parse_datetime(data["updated_at"]),
            closed_at=_parse_datetime(data.get("closed_at")),
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return parsedate_to_datetime(value)
