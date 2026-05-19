"""Service layer for KG read APIs used by FastAPI routes."""

from __future__ import annotations

from typing import Any

from .client import Neo4jClient, Neo4jUnavailableError


class KGService:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def close(self) -> None:
        await self._client.close()

    async def ensure_constraints(self) -> None:
        await self._client.ensure_constraints()

    async def stats(self) -> dict[str, Any]:
        node_rows = await self._client.run(
            """
MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY label
"""
        )
        edge_rows = await self._client.run(
            """
MATCH ()-[r]->()
RETURN type(r) AS type, count(*) AS count
ORDER BY type
"""
        )
        return {
            "nodes": {row["label"]: int(row["count"]) for row in node_rows if row["label"]},
            "edges": {row["type"]: int(row["count"]) for row in edge_rows if row["type"]},
            "degraded": False,
        }

    async def subgraph(self, center: str, hops: int = 1, limit: int = 300) -> dict[str, Any]:
        rows = await self._client.run(
            """
MATCH (c)
WHERE toLower(coalesce(c.full_name, c.name, c.login, c.path, c.title, '')) = toLower($center)
WITH c
MATCH p=(c)-[*1..$hops]-(n)
WITH collect(DISTINCT nodes(p)) AS node_groups, collect(DISTINCT relationships(p)) AS rel_groups
WITH apoc.coll.toSet(apoc.coll.flatten(node_groups)) AS nodes,
     apoc.coll.toSet(apoc.coll.flatten(rel_groups)) AS rels
RETURN
  [n IN nodes[..$limit] | {
    id: toString(id(n)),
    label: labels(n)[0],
    key: coalesce(n.full_name, n.name, n.login, n.path, n.title, toString(id(n))),
    props: properties(n)
  }] AS nodes,
  [r IN rels[..$limit] | {
    id: toString(id(r)),
    source: toString(id(startNode(r))),
    target: toString(id(endNode(r))),
    type: type(r),
    props: properties(r)
  }] AS edges
"""
            ,
            center=center,
            hops=max(1, hops),
            limit=max(1, limit),
        )
        if not rows:
            return {"nodes": [], "edges": [], "degraded": False}
        return {
            "nodes": rows[0].get("nodes", []),
            "edges": rows[0].get("edges", []),
            "degraded": False,
        }

    async def safe_stats(self) -> dict[str, Any]:
        try:
            return await self.stats()
        except Neo4jUnavailableError:
            return {"nodes": {}, "edges": {}, "degraded": True}

    async def safe_subgraph(self, center: str, hops: int, limit: int) -> dict[str, Any]:
        try:
            return await self.subgraph(center=center, hops=hops, limit=limit)
        except Neo4jUnavailableError:
            return {"nodes": [], "edges": [], "degraded": True}
