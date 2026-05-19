"""Wrappers around two embedding spaces:
* `bge-base-zh-v1.5` for Chinese/English natural-language docs
* `microsoft/unixcoder-base` for source code

We lazily import the heavy ML deps so the FastAPI process boots fast
even when these embeddings are not used (e.g. running BM25-only queries).
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings


@lru_cache
def get_text_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_text_model)


@lru_cache
def get_code_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_code_model)


def encode_text(batch: list[str]) -> list[list[float]]:
    return get_text_encoder().encode(batch, normalize_embeddings=True).tolist()


def encode_code(batch: list[str]) -> list[list[float]]:
    return get_code_encoder().encode(batch, normalize_embeddings=True).tolist()
