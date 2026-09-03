from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    analytics_router,
    chat_router,
    diet_router,
    expense_router,
    gmail_router,
    transaction_router,
    voice_router,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.database import init_db
from app.services.gmail_background_sync import gmail_sync_loop


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    sync_task = asyncio.create_task(gmail_sync_loop())
    yield
    sync_task.cancel()
    try:
        await asyncio.wait_for(sync_task, timeout=3)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Expense Agent API",
        version="1.0.0",
        description="Payment ingestion, AI classification, and expense tracking",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=(
            r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):(3000|3005)"
            r"|https://([a-z0-9-]+\.)*netlify\.app"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(transaction_router)
    app.include_router(expense_router)
    app.include_router(diet_router)
    app.include_router(analytics_router)
    app.include_router(chat_router)
    app.include_router(gmail_router)
    app.include_router(voice_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
