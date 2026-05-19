"""Async Neo4j wrapper with pooled connections and retry."""

from __future__ import annotations

import asyncio
from importlib.util import find_spec
from typing import Any

from ..config import get_settings
from .schema import CONSTRAINTS_CYPHER


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j is unreachable after retries."""


class Neo4jClient:
    def __init__(self) -> None:
        if find_spec("neo4j") is None:
            raise Neo4jUnavailableError(
                "neo4j driver is not installed. Install dependencies first."
            )
        from neo4j import AsyncGraphDatabase

        s = get_settings()
        self._retry_attempts = max(1, s.neo4j_request_retries)
        self._retry_backoff = max(0.1, s.neo4j_request_retry_backoff_seconds)
        self._retry_max_backoff = max(
            self._retry_backoff, s.neo4j_request_retry_max_backoff_seconds
        )
        self._driver = AsyncGraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
            max_connection_pool_size=s.neo4j_pool_size,
            connection_timeout=s.neo4j_connection_timeout,
            max_transaction_retry_time=s.neo4j_max_transaction_retry_time,
        )

    async def close(self) -> None:
        await self._driver.close()

    async def verify_connectivity(self) -> None:
        await self._driver.verify_connectivity()

    async def ensure_constraints(self) -> None:
        async with self._driver.session() as s:
            for ddl in CONSTRAINTS_CYPHER:
                await s.run(ddl)

    async def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        async def _execute() -> list[dict[str, Any]]:
            async with self._driver.session() as s:
                result = await s.run(cypher, **params)
                return [record.data() async for record in result]

        return await self._with_retry(_execute)

    async def execute_write(
        self,
        cypher: str,
        rows: list[dict[str, Any]],
        *,
        batch_size: int = 5000,
    ) -> list[dict[str, Any]]:
        async def _execute() -> list[dict[str, Any]]:
            async with self._driver.session() as s:
                result = await s.run(cypher, rows=rows, batch_size=batch_size)
                return [record.data() async for record in result]

        return await self._with_retry(_execute)

    async def _with_retry(self, fn: Any) -> list[dict[str, Any]]:
        from neo4j.exceptions import Neo4jError, ServiceUnavailable

        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await fn()
            except (ServiceUnavailable, Neo4jError) as exc:
                last_exc = exc
                if attempt >= self._retry_attempts:
                    break
                backoff = min(
                    self._retry_backoff * (2 ** (attempt - 1)),
                    self._retry_max_backoff,
                )
                await asyncio.sleep(backoff)
        raise Neo4jUnavailableError(
            "Neo4j request failed after retries."
        ) from last_exc
