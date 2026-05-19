from __future__ import annotations

from backend.app.vector import client, embeddings
from backend.app.vector.cache import SQLiteEmbeddingCache, make_embedding_key, make_text_hash
from backend.app.vector.embeddings import CodeEmbeddingInput


def test_embedding_cache_persists_vectors_and_stats(tmp_path) -> None:
    cache = SQLiteEmbeddingCache(tmp_path / "embeddings.db")
    try:
        cache.set("text", "model-a", "hello", [0.1, 0.2])
        assert cache.get("text", "model-a", "hello") == [0.1, 0.2]
        assert cache.get("text", "model-a", "missing") is None
        stats = cache.stats()
    finally:
        cache.close()

    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["rows"] == 1
    assert make_embedding_key("text", "model-a", "hello").endswith(make_text_hash("hello"))


def test_encode_text_reuses_sqlite_cache(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_encode(batch: list[str], _backend: str) -> list[list[float]]:
        calls.append(batch)
        return [[float(len(text))] for text in batch]

    monkeypatch.setattr(embeddings, "_encode_text_uncached", fake_encode)
    cache = SQLiteEmbeddingCache(tmp_path / "embeddings.db")
    try:
        assert embeddings.encode_text(["alpha"], cache=cache) == [[5.0]]
        assert embeddings.encode_text(["alpha"], cache=cache) == [[5.0]]
    finally:
        cache.close()

    assert calls == [["alpha"]]


def test_encode_code_accepts_language_code_batches(monkeypatch, tmp_path) -> None:
    payloads: list[str] = []

    def fake_encode(batch: list[str], _backend: str) -> list[list[float]]:
        payloads.extend(batch)
        return [[1.0, 2.0, 3.0] for _ in batch]

    monkeypatch.setattr(embeddings, "_encode_code_uncached", fake_encode)
    cache = SQLiteEmbeddingCache(tmp_path / "embeddings.db")
    try:
        vectors = embeddings.encode_code(
            [CodeEmbeddingInput(language="python", code="print('x')"), ("typescript", "foo()")],
            cache=cache,
        )
    finally:
        cache.close()

    assert vectors == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert payloads[0].startswith("language: python\ncode:\n")
    assert payloads[1].startswith("language: typescript\ncode:\n")


def test_ensure_collections_creates_three_named_collections(monkeypatch) -> None:
    seen: list[tuple[str, int]] = []

    def fake_ensure(name: str, dim: int):
        seen.append((name, dim))
        return name

    monkeypatch.setattr(client, "connect", lambda: None)
    monkeypatch.setattr(client, "_ensure_collection", fake_ensure)

    collections = client.ensure_collections(text_dim=768, code_dim=768)

    assert set(collections) == {client.ISSUES_TEXT, client.CODE_CHUNKS, client.PR_TITLES}
    assert seen == [
        (client.ISSUES_TEXT, 768),
        (client.CODE_CHUNKS, 768),
        (client.PR_TITLES, 768),
    ]


def test_bulk_insert_batches_rows(monkeypatch) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.inserts = []
            self.flushes = 0

        def insert(self, columns):
            self.inserts.append(columns)

        def flush(self):
            self.flushes += 1

    fake = FakeCollection()
    monkeypatch.setattr(client, "connect", lambda: None)
    monkeypatch.setattr(client, "_ensure_collection", lambda _name, _dim: fake)

    rows = [
        client.VectorRow(pk=str(idx), repo="owner/repo", ref=f"issue:{idx}", text="body", vec=[0.1])
        for idx in range(5)
    ]

    inserted = client.bulk_insert(client.ISSUES_TEXT, rows, batch_size=2)

    assert inserted == 5
    assert [len(columns[0]) for columns in fake.inserts] == [2, 2, 1]
    assert fake.flushes == 1


def test_search_uses_repo_lang_filter(monkeypatch) -> None:
    class FakeHit:
        score = 0.9
        entity = {
            "pk": "1",
            "repo": "owner/repo",
            "ref": "src/app.py",
            "lang": "python",
            "text": "def main(): pass",
        }

    class FakeCollection:
        def search(self, **kwargs):
            assert kwargs["expr"] == 'repo == "owner/repo" and lang == "python"'
            assert kwargs["limit"] == 3
            return [[FakeHit()]]

    monkeypatch.setattr(client, "connect", lambda: None)
    monkeypatch.setattr(client, "_ensure_collection", lambda _name, _dim: FakeCollection())

    results = client.search(
        client.CODE_CHUNKS,
        [0.1, 0.2],
        top_k=3,
        repo="owner/repo",
        lang="python",
    )

    assert results[0].pk == "1"
    assert results[0].collection == client.CODE_CHUNKS
    assert results[0].score == 0.9


def test_build_filter_expr_escapes_quotes() -> None:
    assert client.build_filter_expr(repo='owner/"repo"', lang="py") == (
        'repo == "owner/\\"repo\\"" and lang == "py"'
    )
