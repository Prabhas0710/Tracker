"""ChatGPT-style conversations: list, open, and backfill legacy messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChatConversation, ChatMessage
from app.schemas.chat_schema import ChatConversationDetail, ChatConversationOut, ChatMessageOut

IDLE_GAP = timedelta(hours=3)


def title_from_message(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return "New chat"
    if len(cleaned) <= 52:
        return cleaned
    return cleaned[:49].rstrip() + "…"


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ChatHistoryService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _user_id(self) -> int:
        return self.settings.default_user_id

    def ensure_conversation(
        self,
        conversation_id: Optional[int] = None,
        *,
        title_from: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ChatConversation:
        user_id = user_id or self._user_id()
        if conversation_id:
            conv = (
                self.db.query(ChatConversation)
                .filter(ChatConversation.id == conversation_id, ChatConversation.user_id == user_id)
                .first()
            )
            if conv:
                return conv
        conv = ChatConversation(
            user_id=user_id,
            title=title_from_message(title_from or ""),
        )
        self.db.add(conv)
        self.db.flush()
        return conv

    def touch(self, conv: ChatConversation, title_from: Optional[str] = None) -> None:
        if title_from and (not conv.title or conv.title == "New chat"):
            conv.title = title_from_message(title_from)
        conv.updated_at = datetime.now(timezone.utc)

    def list_conversations(self) -> list[ChatConversationOut]:
        self.backfill()
        user_id = self._user_id()
        rows = (
            self.db.query(ChatConversation)
            .filter(ChatConversation.user_id == user_id)
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
            .all()
        )
        out: list[ChatConversationOut] = []
        for conv in rows:
            messages = [
                row
                for row in conv.messages
                if row.role in {"user", "assistant"}
            ]
            user_messages = [row for row in messages if row.role == "user"]
            if not user_messages:
                continue
            preview = next(
                (row.content for row in reversed(messages) if row.content.strip()),
                "",
            )
            out.append(
                ChatConversationOut(
                    id=conv.id,
                    title=conv.title or title_from_message(user_messages[0].content),
                    preview=" ".join(preview.split())[:140],
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=len(messages),
                )
            )
        return out

    def get_conversation(self, conversation_id: int) -> Optional[ChatConversationDetail]:
        self.backfill()
        conv = (
            self.db.query(ChatConversation)
            .filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == self._user_id(),
            )
            .first()
        )
        if not conv:
            return None
        messages = [
            ChatMessageOut(role=row.role, content=row.content, created_at=row.created_at)
            for row in conv.messages
            if row.role in {"user", "assistant"}
        ]
        user_messages = [row for row in messages if row.role == "user"]
        preview = next((row.content for row in reversed(messages) if row.content.strip()), "")
        return ChatConversationDetail(
            id=conv.id,
            title=conv.title or (title_from_message(user_messages[0].content) if user_messages else "New chat"),
            preview=" ".join(preview.split())[:140],
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=len(messages),
            messages=messages,
        )

    def delete_conversation(self, conversation_id: int) -> bool:
        conv = (
            self.db.query(ChatConversation)
            .filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == self._user_id(),
            )
            .first()
        )
        if not conv:
            return False
        self.db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).delete()
        self.db.delete(conv)
        self.db.commit()
        return True

    def conversation_messages(self, conversation_id: int) -> list[dict[str, str]]:
        detail = self.get_conversation(conversation_id)
        if not detail:
            return []
        return [{"role": row.role, "content": row.content} for row in detail.messages]

    def backfill(self) -> int:
        """Group legacy messages (no conversation_id) into chats."""
        orphans = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.conversation_id.is_(None))
            .order_by(ChatMessage.id.asc())
            .all()
        )
        if not orphans:
            return 0

        current: Optional[ChatConversation] = None
        last_ts: Optional[datetime] = None
        had_user = False
        created = 0

        for msg in orphans:
            ts = _aware(msg.created_at)
            welcome = msg.role == "assistant" and (msg.content or "").startswith("Welcome back")
            gap = bool(current and last_ts and ts and ts - last_ts > IDLE_GAP)
            new_day_welcome = bool(current and welcome and had_user)
            if current is None or gap or new_day_welcome:
                current = ChatConversation(
                    user_id=msg.user_id,
                    title="New chat",
                    created_at=msg.created_at or datetime.now(timezone.utc),
                    updated_at=msg.created_at or datetime.now(timezone.utc),
                )
                self.db.add(current)
                self.db.flush()
                created += 1
                had_user = False
            msg.conversation_id = current.id
            if msg.role == "user" and (current.title == "New chat" or not current.title):
                current.title = title_from_message(msg.content)
                had_user = True
            elif msg.role == "user":
                had_user = True
            if ts:
                current.updated_at = ts
                last_ts = ts

        self.db.commit()
        return created
