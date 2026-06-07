"""
Module: app
Layer: api
Purpose: FastAPI application instance for the Tributary demo UI. Mounts static files
    and registers the demo API router.
Dependencies: fastapi, tributary.api.routes
Used by: uvicorn entry point (uvicorn tributary.api.app:app)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tributary.api.routes import router

_STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"

app = FastAPI(title="Tributary Demo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    """Serve the demo UI index page."""
    return FileResponse(str(_STATIC_DIR / "index.html"))
