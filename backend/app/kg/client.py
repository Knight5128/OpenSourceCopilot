"""Thin Neo4j driver wrapper used everywhere we need Cypher."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase, Session

from ..config import get_settings
from .schema import CONSTRAINTS_CYPHER


class Neo4jClient:
    def __init__(self) -> None:
        s = get_settings()
        self._driver = GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
        )

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def session(self) -> Iterable[Session]:
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    def ensure_constraints(self) -> None:
        with self.session() as s:
            for ddl in CONSTRAINTS_CYPHER:
                s.run(ddl)

    def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        with self.session() as s:
            return [r.data() for r in s.run(cypher, **params)]
