"""Vercel serverless entrypoint for DINESYNC."""

from backend.app.main import app

__all__ = ["app"]
