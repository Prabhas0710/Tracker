from datetime import datetime, timedelta, timezone

from app.models import ChatMessage
from app.services.assistant_service import AssistantService
from app.services.chat_history_service import ChatHistoryService


def test_reply_creates_conversation_and_history_list(db):
    bot = AssistantService(db)
    first = bot.reply("what are my expenses yesterday")
    assert first.conversation_id is not None

    second = bot.reply("did I meet my diet goals", conversation_id=first.conversation_id)
    assert second.conversation_id == first.conversation_id

    chats = ChatHistoryService(db).list_conversations()
    assert len(chats) == 1
    assert "expenses yesterday" in chats[0].title.lower()
    assert chats[0].message_count == 4

    detail = ChatHistoryService(db).get_conversation(first.conversation_id)
    assert detail is not None
    assert [row.role for row in detail.messages] == ["user", "assistant", "user", "assistant"]


def test_new_chat_without_id_starts_another_conversation(db):
    bot = AssistantService(db)
    one = bot.reply("first chat")
    two = bot.reply("second chat")
    assert one.conversation_id != two.conversation_id
    chats = ChatHistoryService(db).list_conversations()
    assert len(chats) == 2


def test_welcome_only_messages_are_hidden_from_history(db):
    db.add(ChatMessage(user_id=1, role="assistant", content="Welcome back, Prabhas.\nAsk me anything."))
    db.commit()
    chats = ChatHistoryService(db).list_conversations()
    assert chats == []


def test_backfill_splits_idle_chats(db):
    older = datetime.now(timezone.utc) - timedelta(hours=8)
    newer = datetime.now(timezone.utc)
    db.add(ChatMessage(user_id=1, role="user", content="old question", created_at=older))
    db.add(ChatMessage(user_id=1, role="assistant", content="old answer", created_at=older))
    db.add(ChatMessage(user_id=1, role="user", content="new question", created_at=newer))
    db.add(ChatMessage(user_id=1, role="assistant", content="new answer", created_at=newer))
    db.commit()

    chats = ChatHistoryService(db).list_conversations()
    assert len(chats) == 2
    titles = {row.title.lower() for row in chats}
    assert "old question" in titles
    assert "new question" in titles


def test_delete_conversation(db):
    bot = AssistantService(db)
    result = bot.reply("delete me later")
    ok = ChatHistoryService(db).delete_conversation(result.conversation_id)
    assert ok is True
    assert ChatHistoryService(db).list_conversations() == []
    assert ChatHistoryService(db).get_conversation(result.conversation_id) is None
