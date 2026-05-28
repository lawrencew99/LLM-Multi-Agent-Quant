"""FastAPI app for NewsAlpha — exposes snapshots, replay, memory, and events."""

from __future__ import annotations

from newsalpha.api.app import create_app

__all__ = ["create_app"]
