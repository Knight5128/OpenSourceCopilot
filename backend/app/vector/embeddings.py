"""Wrappers around two embedding spaces:
* `bge-base-zh-v1.5` for Chinese/English natural-language docs
* `microsoft/unixcoder-base` for source code

We lazily import the heavy ML deps so the FastAPI process boots fast
even when these embeddings are not used (e.g. running BM25-only queries).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..config import get_settings
from .cache import SQLiteEmbeddingCache


@lru_cache
def get_text_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_text_model)


@lru_cache
def get_code_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_code_model)


@lru_cache
def get_embedding_cache() -> SQLiteEmbeddingCache:
    return SQLiteEmbeddingCache(get_settings().embedding_cache_db_path)


@dataclass(frozen=True)
class CodeEmbeddingInput:
    language: str
    code: str


def encode_text(
    batch: list[str],
    *,
    cache: SQLiteEmbeddingCache | None = None,
    use_cache: bool = True,
) -> list[list[float]]:
    """Embed natural-language text with optional SQLite reuse."""

    if not batch:
        return []
    settings = get_settings()
    model = _active_text_model()
    embedding_cache = cache or (get_embedding_cache() if use_cache else None)
    return _encode_with_cache(
        space="text",
        model=model,
        payloads=batch,
        cache=embedding_cache,
        encode_missing=lambda missing: _encode_text_uncached(missing, settings.embedding_backend),
    )


def encode_code(
    batch: list[CodeEmbeddingInput | tuple[str, str] | str],
    *,
    cache: SQLiteEmbeddingCache | None = None,
    use_cache: bool = True,
) -> list[list[float]]:
    """Embed source code snippets.

    Items may be `CodeEmbeddingInput`, `(language, code)` tuples, or raw code strings.
    The language is included in the encoded payload so batch and single-item calls use
    the same embedding space.
    """

    if not batch:
        return []
    settings = get_settings()
    payloads = [_normalise_code_payload(item) for item in batch]
    model = _active_code_model()
    embedding_cache = cache or (get_embedding_cache() if use_cache else None)
    return _encode_with_cache(
        space="code",
        model=model,
        payloads=payloads,
        cache=embedding_cache,
        encode_missing=lambda missing: _encode_code_uncached(missing, settings.embedding_backend),
    )


def _encode_with_cache(
    *,
    space: str,
    model: str,
    payloads: list[str],
    cache: SQLiteEmbeddingCache | None,
    encode_missing,
) -> list[list[float]]:
    if cache is None:
        return encode_missing(payloads)

    cached = cache.get_many(space, model, payloads)
    result: list[list[float] | None] = list(cached)
    missing_positions = [idx for idx, vector in enumerate(cached) if vector is None]
    if missing_positions:
        missing_payloads = [payloads[idx] for idx in missing_positions]
        missing_vectors = encode_missing(missing_payloads)
        for idx, vector in zip(missing_positions, missing_vectors, strict=True):
            result[idx] = vector
            cache.set(space, model, payloads[idx], vector)
    return [vector for vector in result if vector is not None]


def _encode_text_uncached(batch: list[str], backend: str) -> list[list[float]]:
    if backend.lower() in {"api", "openai"}:
        return _encode_api(batch, _active_text_model())
    return get_text_encoder().encode(batch, normalize_embeddings=True).tolist()


def _encode_code_uncached(batch: list[str], backend: str) -> list[list[float]]:
    if backend.lower() in {"api", "openai"}:
        return _encode_api(batch, _active_code_model())
    return get_code_encoder().encode(batch, normalize_embeddings=True).tolist()


def _encode_api(batch: list[str], model: str) -> list[list[float]]:
    settings = get_settings()
    from openai import OpenAI

    kwargs = {"api_key": settings.embedding_api_key or settings.llm_api_key}
    if settings.embedding_api_base_url:
        kwargs["base_url"] = settings.embedding_api_base_url
    elif settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    client = OpenAI(**kwargs)
    response = client.embeddings.create(model=model, input=batch)
    return [item.embedding for item in response.data]


def _normalise_code_payload(item: CodeEmbeddingInput | tuple[str, str] | str) -> str:
    if isinstance(item, CodeEmbeddingInput):
        language, code = item.language, item.code
    elif isinstance(item, tuple):
        language, code = item
    else:
        language, code = "text", item
    return f"language: {language}\ncode:\n{code}"


def _active_text_model() -> str:
    settings = get_settings()
    if (
        settings.embedding_backend.lower() in {"api", "openai"}
        and settings.embedding_api_text_model
    ):
        return settings.embedding_api_text_model
    return settings.embedding_text_model


def _active_code_model() -> str:
    settings = get_settings()
    if (
        settings.embedding_backend.lower() in {"api", "openai"}
        and settings.embedding_api_code_model
    ):
        return settings.embedding_api_code_model
    return settings.embedding_code_model
