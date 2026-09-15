"""Vercel entry point for Barcode Reader API.

Exposes the FastAPI application for serverless deployment.
Vercel imports the `app` instance directly; do not start uvicorn here.
"""

from app_vercel import app

__all__ = ["app"]