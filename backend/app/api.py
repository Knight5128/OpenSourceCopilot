"""FastAPI route definitions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .schemas import OnboardingPlan, OnboardingRequest

router = APIRouter(prefix="/api/v1", tags=["copilot"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
