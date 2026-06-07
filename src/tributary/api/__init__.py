"""
Package: tributary.api
Layer: api
Purpose: HTTP routes and request/response models for the Tributary FastAPI application.
Public surface: app (FastAPI instance for uvicorn)
"""
from __future__ import annotations

from tributary.api.app import app

__all__ = ["app"]
