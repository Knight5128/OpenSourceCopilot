"""Milvus collection helpers.

Two collections:
* `issues_text` ─ 768-dim BGE embeddings of Issue title + body
* `code_chunks` ─ 768-dim UniXcoder embeddings of code chunks
"""

from __future__ import annotations

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from ..config import get_settings

ISSUE_TEXT = "issues_text"
CODE_CHUNKS = "code_chunks"


def connect() -> None:
    s = get_settings()
    connections.connect(alias="default", host=s.milvus_host, port=s.milvus_port)


def _ensure_collection(name: str, dim: int) -> Collection:
    if utility.has_collection(name):
        return Collection(name)
    fields = [
        FieldSchema(name="pk", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
        FieldSchema(name="repo", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="ref", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8192),
        FieldSchema(name="vec", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    coll = Collection(name, CollectionSchema(fields, description=name))
    coll.create_index(
        "vec",
        index_params={"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 128}},
    )
    coll.load()
    return coll


def ensure_collections(text_dim: int = 768, code_dim: int = 768) -> None:
    connect()
    _ensure_collection(ISSUE_TEXT, text_dim)
    _ensure_collection(CODE_CHUNKS, code_dim)
