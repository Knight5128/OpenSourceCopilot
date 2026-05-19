"""FastAPI route definitions."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from .kg.client import Neo4jClient
from .kg.service import KGService
from .schemas import KGStatsResponse, KGSubgraphResponse, OnboardingPlan, OnboardingRequest

router = APIRouter(prefix="/api/v1", tags=["copilot"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@lru_cache
def get_kg_service() -> KGService:
    client = Neo4jClient()
    return KGService(client)


@router.post("/onboarding/plan", response_model=OnboardingPlan)
def create_onboarding_plan(req: OnboardingRequest) -> OnboardingPlan:
    """End-to-end entrypoint that invokes the LangGraph agent.

    Implementation will be filled in during Week 3. Returns 501 for now
    so the frontend can wire up against a stable contract immediately.
    """

    raise HTTPException(
        status_code=501,
        detail="Agent pipeline not yet wired. See backend/app/agent/graph.py.",
    )


@router.get("/kg/stats", response_model=KGStatsResponse)
async def get_kg_stats() -> KGStatsResponse:
    data = await get_kg_service().safe_stats()
    return KGStatsResponse(**data)


@router.get("/kg/subgraph", response_model=KGSubgraphResponse)
async def get_kg_subgraph(
    center: str,
    hops: int = 1,
    limit: int = 300,
) -> KGSubgraphResponse:
    data = await get_kg_service().safe_subgraph(center=center, hops=hops, limit=limit)
    return KGSubgraphResponse(**data)
