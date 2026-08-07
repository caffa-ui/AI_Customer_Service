from typing import Protocol, runtime_checkable

from app.conversation.models import Conversation


class ConversationAccessError(PermissionError):
    """会话存在，但不属于当前用户。"""


class ConversationNotFoundError(LookupError):
    """会话不存在。"""


@runtime_checkable
class ConversationRepository(Protocol):
    """会话归属 Repository；Checkpoint 内容由 LangGraph 单独维护。"""

    async def ensure_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        """不存在时创建会话，存在时校验其归属并刷新访问时间。"""
        ...

    async def get_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation | None:
        ...

    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[Conversation]:
        ...

    async def delete_owned(self, conversation_id: str, user_id: str) -> bool:
        ...
