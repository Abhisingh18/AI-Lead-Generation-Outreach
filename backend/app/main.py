"""FastAPI application entrypoint."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import router
from app.config import settings
from app.database import init_db

# Configure logging
logger.remove()
logger.add(sys.stderr, level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Lead Gen Platform ({} env)", settings.app_env)
    init_db()  # create tables on startup (MVP). Use Alembic for real migrations.
    logger.info("Database initialized. LLM provider: {}", settings.llm_provider)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="AI Lead Generation & Outreach Platform",
    version="0.1.0",
    description="Scrape local-business leads, audit their web presence with AI, "
    "score them, and generate personalized WhatsApp outreach.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production (set your frontend origin)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": app.version, "llm_provider": settings.llm_provider}
