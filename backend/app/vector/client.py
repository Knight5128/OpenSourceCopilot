"""Milvus collection helpers for issues, code chunks, and PR titles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when dependency is absent
    Collection = Any
    CollectionSchema = DataType = FieldSchema = connections = utility = None
    _PYMILVUS_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _PYMILVUS_IMPORT_ERROR = None

from ..config import get_settings

ISSUES_TEXT = "issues_text"
ISSUE_TEXT = ISSUES_TEXT
CODE_CHUNKS = "code_chunks"
PR_TITLES = "pr_titles"

VECTOR_FIELD = "vec"
OUTPUT_FIELDS = ["pk", "repo", "ref", "lang", "text"]


@dataclass(frozen=True)
class VectorRow:
    pk: str
    repo: str
    ref: str
    text: str
    vec: list[float]
    lang: str = ""


@dataclass(frozen=True)
class VectorSearchResult:
    pk: str
    repo: str
    ref: str
    text: str
    score: float
    collection: str
    lang: str = ""


def connect() -> None:
    _require_pymilvus()
    s = get_settings()
    connections.connect(alias="default", host=s.milvus_host, port=s.milvus_port)


def ensure_collections(
    text_dim: int | None = None,
    code_dim: int | None = None,
) -> dict[str, Collection]:
    """Create and load all vector collections required by M3."""

    connect()
    text_dim = text_dim or get_settings().embedding_dim
    code_dim = code_dim or get_settings().embedding_dim
    return {
        ISSUES_TEXT: _ensure_collection(ISSUES_TEXT, text_dim),
        CODE_CHUNKS: _ensure_collection(CODE_CHUNKS, code_dim),
        PR_TITLES: _ensure_collection(PR_TITLES, text_dim),
    }


def bulk_insert(
    collection_name: str,
    rows: list[VectorRow],
    *,
    batch_size: int | None = None,
) -> int:
    """Insert vector rows in batches and flush once at the end."""

    if not rows:
        return 0
    connect()
    coll = _ensure_collection(collection_name, len(rows[0].vec))
    batch_size = batch_size or get_settings().milvus_batch_size
    inserted = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        coll.insert(
            [
                [row.pk for row in chunk],
                [row.repo for row in chunk],
                [row.ref for row in chunk],
                [row.lang for row in chunk],
                [row.text for row in chunk],
                [row.vec for row in chunk],
            ]
        )
        inserted += len(chunk)
    coll.flush()
    return inserted


def search(
    collection_name: str,
    query_vector: list[float],
    *,
    top_k: int = 20,
    repo: str | None = None,
    lang: str | None = None,
) -> list[VectorSearchResult]:
    """Run ANN recall with optional `repo` and `lang` filters."""

    connect()
    coll = _ensure_collection(collection_name, len(query_vector))
    raw_hits = coll.search(
        data=[query_vector],
        anns_field=VECTOR_FIELD,
        param=_search_params(),
        limit=top_k,
        expr=build_filter_expr(repo=repo, lang=lang),
        output_fields=OUTPUT_FIELDS,
    )
    if not raw_hits:
        return []
    return [_hit_to_result(collection_name, hit) for hit in raw_hits[0]]


def build_filter_expr(*, repo: str | None = None, lang: str | None = None) -> str | None:
    clauses: list[str] = []
    if repo:
        clauses.append(f'repo == "{_escape_expr_value(repo)}"')
    if lang:
        clauses.append(f'lang == "{_escape_expr_value(lang)}"')
    return " and ".join(clauses) if clauses else None


def _ensure_collection(name: str, dim: int) -> Collection:
    _require_pymilvus()
    if utility.has_collection(name):
        coll = Collection(name)
        coll.load()
        return coll

    fields = [
        FieldSchema(name="pk", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
        FieldSchema(name="repo", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="ref", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="lang", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8192),
        FieldSchema(name=VECTOR_FIELD, dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    coll = Collection(name, CollectionSchema(fields, description=name))
    coll.create_index(VECTOR_FIELD, index_params=_index_params())
    coll.load()
    return coll


def _index_params() -> dict:
    settings = get_settings()
    return {
        "index_type": settings.milvus_index_type,
        "metric_type": settings.milvus_metric_type,
        "params": {"nlist": settings.milvus_index_nlist},
    }


def _search_params() -> dict:
    settings = get_settings()
    return {
        "metric_type": settings.milvus_metric_type,
        "params": {"nprobe": settings.milvus_search_nprobe},
    }


def _hit_to_result(collection_name: str, hit) -> VectorSearchResult:
    entity = hit.entity
    get_value = entity.get if hasattr(entity, "get") else lambda key: getattr(entity, key)
    return VectorSearchResult(
        pk=str(get_value("pk")),
        repo=str(get_value("repo")),
        ref=str(get_value("ref")),
        lang=str(get_value("lang") or ""),
        text=str(get_value("text") or ""),
        score=float(hit.score),
        collection=collection_name,
    )


def _escape_expr_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _require_pymilvus() -> None:
    if _PYMILVUS_IMPORT_ERROR is not None:
        raise RuntimeError(
            "pymilvus is required for vector storage. Install project requirements "
            "before connecting to Milvus."
        ) from _PYMILVUS_IMPORT_ERROR
