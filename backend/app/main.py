"""FastAPI application entrypoint.

Run locally with:
    uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="OpenSourceCopilot",
    version="0.1.0",
    description="KG + HybridRAG + Agent copilot for open-source onboarding.",
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
