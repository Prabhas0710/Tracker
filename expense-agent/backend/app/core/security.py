"""Lightweight security helpers for MVP (optional mock ingest API key)."""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def verify_mock_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.mock_ingest_api_key:
        return
    if x_api_key != settings.mock_ingest_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
