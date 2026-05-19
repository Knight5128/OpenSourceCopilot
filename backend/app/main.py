"""FastAPI application entrypoint.

Run locally with:
    uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import get_kg_service, router as api_router
from .config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await get_kg_service().ensure_constraints()
    except Exception as exc:  # pragma: no cover - startup should not hard-fail in dev
        logging.getLogger(__name__).warning("KG init skipped: %s", exc)
    yield
    if get_kg_service.cache_info().currsize > 0:
        kg_service = get_kg_service()
        await kg_service.close()


app = FastAPI(
    title="OpenSourceCopilot",
    version="0.1.0",
    description="KG + HybridRAG + Agent copilot for open-source onboarding.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def index() -> dict[str, str]:
    return {"service": "OpenSourceCopilot", "version": app.version}
