from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables, apply light migrations, and seed baseline data."""
    from sqlalchemy import text

    from app.database.seed import seed_database  # noqa: WPS433
    from app.models import ChatConversation, Meal, MealMemory, PushSubscription  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # Multi-Gmail: allow multiple accounts per user
        conn.execute(text("ALTER TABLE gmail_credentials DROP CONSTRAINT IF EXISTS uq_gmail_user"))
        conn.execute(
            text(
                "ALTER TABLE gmail_synced_messages "
                "ADD COLUMN IF NOT EXISTS gmail_account VARCHAR(255)"
            )
        )
        # Fill null emails before NOT NULL (legacy rows)
        conn.execute(
            text(
                "UPDATE gmail_credentials SET email = CONCAT('unknown+', id::text, '@local') "
                "WHERE email IS NULL OR trim(email) = ''"
            )
        )
        try:
            conn.execute(text("ALTER TABLE gmail_credentials ALTER COLUMN email SET NOT NULL"))
        except Exception:
            pass
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_user_email "
                "ON gmail_credentials (user_id, email)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_account_message "
                "ON gmail_synced_messages (gmail_account, gmail_message_id)"
            )
        )
        # Legacy single-column unique blocked multi-inbox sync (same Gmail id, two accounts)
        conn.execute(text("ALTER TABLE gmail_synced_messages DROP CONSTRAINT IF EXISTS uq_gmail_message"))
        conn.execute(text("DROP INDEX IF EXISTS uq_gmail_message"))
        conn.execute(
            text(
                "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS direction VARCHAR(16) DEFAULT 'debit'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS direction VARCHAR(16) DEFAULT 'debit'"
            )
        )
        conn.execute(text("UPDATE expenses SET direction = 'debit' WHERE direction IS NULL"))
        conn.execute(text("UPDATE transactions SET direction = 'debit' WHERE direction IS NULL"))
        conn.execute(text("ALTER TABLE meals ADD COLUMN IF NOT EXISTS fiber FLOAT"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title VARCHAR(255) NOT NULL DEFAULT 'New chat',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                "ALTER TABLE chat_messages "
                "ADD COLUMN IF NOT EXISTS conversation_id INTEGER REFERENCES chat_conversations(id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_conversation_id "
                "ON chat_messages (conversation_id)"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chat_conversations_user_id ON chat_conversations (user_id)")
        )

    db = SessionLocal()
    try:
        seed_database(db)
        db.commit()
        from app.services.chat_history_service import ChatHistoryService

        ChatHistoryService(db).backfill()
    finally:
        db.close()
