"""Deployment entrypoint. The application lives in backend.app.main."""

from backend.app.main import app

__all__ = ["app"]
