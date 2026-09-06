from app.api.analytics_routes import router as analytics_router
from app.api.chat_routes import router as chat_router
from app.api.credit_card_routes import router as credit_card_router
from app.api.diet_routes import router as diet_router
from app.api.expense_routes import router as expense_router
from app.api.gmail_routes import router as gmail_router
from app.api.transaction_routes import router as transaction_router
from app.api.voice_routes import router as voice_router

__all__ = [
    "analytics_router",
    "chat_router",
    "credit_card_router",
    "diet_router",
    "expense_router",
    "transaction_router",
    "gmail_router",
    "voice_router",
]
