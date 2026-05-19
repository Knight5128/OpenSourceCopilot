"""Three-way HybridRAG retriever.

Pipeline:
    query
      ├─ BM25 over Issue text  ─┐
      ├─ Dense vector recall   ─┼─►  union + dedupe  ─►  LLM re-rank  ─►  answer + citations
      └─ Graph hop expansion   ─┘

Member B owns this module. The methods below are typed contracts that
`agent/graph.py` already imports - keep signatures stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import Citation


@dataclass
class RetrievalHit:
    score: float
    source: str  # one of "bm25" | "vector" | "graph"
    citation: Citation
    snippet: str = ""


@dataclass
class HybridResult:
    hits: list[RetrievalHit] = field(default_factory=list)
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)


class HybridRetriever:
    def __init__(self, top_k_each: int = 10, final_k: int = 5) -> None:
        self.top_k_each = top_k_each
        self.final_k = final_k

    # ------------- per-channel ----------------
    def bm25(self, query: str) -> list[RetrievalHit]:
        raise NotImplementedError

    def dense(self, query: str) -> list[RetrievalHit]:
        raise NotImplementedError

    def graph(self, query: str) -> list[RetrievalHit]:
        raise NotImplementedError

    # ------------- top-level ------------------
    def retrieve(self, query: str) -> HybridResult:
        raise NotImplementedError("Week 2 deliverable. See docs/proposal.md §4-Module 3.")
