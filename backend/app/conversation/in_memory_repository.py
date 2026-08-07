import asyncio
from datetime import datetime, timezone

from app.conversation.models import Conversation
from app.conversation.repository import ConversationAccessError


class InMemoryConversationRepository:
    """仅供单元测试使用的会话归属 Repository。"""

    def __init__(self):
        self._conversations: dict[str, Conversation] = {}
        self._lock = asyncio.Lock()

    async def ensure_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        async with self._lock:
            existing = self._conversations.get(conversation_id)
            now = datetime.now(timezone.utc)
            if existing is not None and existing.user_id != user_id:
                raise ConversationAccessError("当前用户无权访问该会话")

            conversation = Conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._conversations[conversation_id] = conversation
            return conversation

    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[Conversation]:
        async with self._lock:
            conversations = sorted(
                (
                    conversation
                    for conversation in self._conversations.values()
                    if conversation.user_id == user_id
                ),
                key=lambda conversation: conversation.updated_at,
                reverse=True,
            )
            return conversations[offset : offset + limit]

    async def get_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation | None:
        async with self._lock:
            existing = self._conversations.get(conversation_id)
            if existing is not None and existing.user_id != user_id:
                raise ConversationAccessError("当前用户无权访问该会话")
            return existing

    async def delete_owned(self, conversation_id: str, user_id: str) -> bool:
        async with self._lock:
            existing = self._conversations.get(conversation_id)
            if existing is None:
                return False
            if existing.user_id != user_id:
                raise ConversationAccessError("当前用户无权访问该会话")
            del self._conversations[conversation_id]
            return True
