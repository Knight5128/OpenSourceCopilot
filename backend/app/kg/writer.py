"""Batch ingestion utilities for Neo4j knowledge graph."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..config import get_settings
from .client import Neo4jClient
from .schema import (
    AFFECTS,
    AUTHORED,
    CALLS,
    CLOSES,
    CONTAINS,
    CONTRIBUTOR,
    FUNCTION,
    HAS_SKILL,
    ISSUE,
    MODIFIES,
    MODULE,
    PR,
    REPO,
    REQUIRES,
    SKILL,
)


class KGBatchWriter:
    """Write graph entities/relations using UNWIND + APOC iterate."""

    def __init__(self, client: Neo4jClient, *, batch_size: int | None = None) -> None:
        settings = get_settings()
        self._client = client
        self._batch_size = batch_size or settings.kg_batch_size

    async def write_nodes(self, label: str, rows: Sequence[dict[str, Any]]) -> int:
        if not rows:
            return 0
        merge_keys = _merge_keys_for_label(label)
        set_props = ", ".join(f"n.{k} = row.{k}" for k in _prop_keys(rows, merge_keys))
        merge_clause = ", ".join(f"{key}: row.{key}" for key in merge_keys)
        if not set_props:
            set_props = "n.updated_at = datetime()"
        cypher = f"""
CALL apoc.periodic.iterate(
  "UNWIND $rows AS row RETURN row",
  "MERGE (n:{label} {{{merge_clause}}})
   SET {set_props}",
  {{batchSize: $batch_size, parallel: false, params: {{rows: $rows}}}}
)
YIELD total
RETURN total
"""
        try:
            result = await self._client.execute_write(
                cypher, rows=list(rows), batch_size=self._batch_size
            )
            return int(result[0]["total"]) if result else len(rows)
        except Exception:
            # Fallback when APOC is unavailable: use plain UNWIND in one transaction.
            fallback = f"""
UNWIND $rows AS row
MERGE (n:{label} {{{merge_clause}}})
SET {set_props}
RETURN count(*) AS total
"""
            result = await self._client.run(
                fallback, rows=list(rows), batch_size=self._batch_size
            )
            return int(result[0]["total"]) if result else len(rows)

    async def write_relationships(
        self,
        rel_type: str,
        rows: Sequence[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        spec = _relationship_spec(rel_type)
        cypher = f"""
CALL apoc.periodic.iterate(
  "UNWIND $rows AS row RETURN row",
  "MATCH (a:{spec['from_label']} {{{spec['from_match']}}})
   MATCH (b:{spec['to_label']} {{{spec['to_match']}}})
   MERGE (a)-[r:{rel_type}]->(b)
   SET r += coalesce(row.rel_props, {{}})",
  {{batchSize: $batch_size, parallel: false, params: {{rows: $rows}}}}
)
YIELD total
RETURN total
"""
        try:
            result = await self._client.execute_write(
                cypher, rows=list(rows), batch_size=self._batch_size
            )
            return int(result[0]["total"]) if result else len(rows)
        except Exception:
            fallback = f"""
UNWIND $rows AS row
MATCH (a:{spec['from_label']} {{{spec['from_match']}}})
MATCH (b:{spec['to_label']} {{{spec['to_match']}}})
MERGE (a)-[r:{rel_type}]->(b)
SET r += coalesce(row.rel_props, {{}})
RETURN count(*) AS total
"""
            result = await self._client.run(fallback, rows=list(rows))
            return int(result[0]["total"]) if result else len(rows)


def _merge_keys_for_label(label: str) -> tuple[str, ...]:
    return {
        REPO: ("full_name",),
        MODULE: ("repo", "path"),
        FUNCTION: ("repo", "module_path", "name"),
        ISSUE: ("repo", "number"),
        PR: ("repo", "number"),
        CONTRIBUTOR: ("login",),
        SKILL: ("name",),
    }.get(label, ("id",))


def _relationship_spec(rel_type: str) -> dict[str, str]:
    specs: dict[str, dict[str, str]] = {
        CONTAINS: {
            "from_label": MODULE,
            "to_label": FUNCTION,
            "from_match": "repo: row.from.repo, path: row.from.path",
            "to_match": "repo: row.to.repo, module_path: row.to.module_path, name: row.to.name",
        },
        CALLS: {
            "from_label": FUNCTION,
            "to_label": FUNCTION,
            "from_match": "repo: row.from.repo, module_path: row.from.module_path, name: row.from.name",
            "to_match": "repo: row.to.repo, module_path: row.to.module_path, name: row.to.name",
        },
        AFFECTS: {
            "from_label": ISSUE,
            "to_label": MODULE,
            "from_match": "repo: row.from.repo, number: row.from.number",
            "to_match": "repo: row.to.repo, path: row.to.path",
        },
        MODIFIES: {
            "from_label": PR,
            "to_label": FUNCTION,
            "from_match": "repo: row.from.repo, number: row.from.number",
            "to_match": "repo: row.to.repo, module_path: row.to.module_path, name: row.to.name",
        },
        CLOSES: {
            "from_label": PR,
            "to_label": ISSUE,
            "from_match": "repo: row.from.repo, number: row.from.number",
            "to_match": "repo: row.to.repo, number: row.to.number",
        },
        AUTHORED: {
            "from_label": CONTRIBUTOR,
            "to_label": PR,
            "from_match": "login: row.from.login",
            "to_match": "repo: row.to.repo, number: row.to.number",
        },
        HAS_SKILL: {
            "from_label": CONTRIBUTOR,
            "to_label": SKILL,
            "from_match": "login: row.from.login",
            "to_match": "name: row.to.name",
        },
        REQUIRES: {
            "from_label": ISSUE,
            "to_label": SKILL,
            "from_match": "repo: row.from.repo, number: row.from.number",
            "to_match": "name: row.to.name",
        },
    }
    if rel_type not in specs:
        raise ValueError(f"Unsupported relationship type: {rel_type}")
    return specs[rel_type]


def _prop_keys(
    rows: Sequence[dict[str, Any]],
    exclude: tuple[str, ...],
) -> list[str]:
    keys = set().union(*(row.keys() for row in rows))
    return [k for k in sorted(keys) if k not in exclude]
