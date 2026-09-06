import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
import re
from typing import Any, Literal
from uuid import uuid4

from langchain_core.messages import BaseMessage, HumanMessage

from app.conversation.repository import (
    ConversationNotFoundError,
    ConversationRepository,
)
from app.conversation.models import Conversation
from app.middleware.agent_monitoring import (
    AgentMonitoringCallback,
    log_request_finished,
    log_request_started,
)
from app.middleware.context import bind_request_context, create_request_context
from app.user.models import UserProfile
from app.user.repository import UserAccessError, UserRepository


@dataclass(frozen=True, slots=True)
class ChatResponse:
    request_id: str
    conversation_id: str
    user_id: str
    content: str
    message_id: str | None


@dataclass(slots=True)
class _ConversationLockEntry:
    lock: asyncio.Lock
    references: int = 0


class ChatService:
    """为 CLI/FastAPI 屏蔽 LangGraph 状态恢复与增量消息细节。"""

    def __init__(
        self,
        graph: Any,
        conversation_repository: ConversationRepository,
        user_repository: UserRepository | None = None,
    ):
        self.graph = graph
        self.conversation_repository = conversation_repository
        self.user_repository = user_repository
        self._conversation_locks: dict[str, _ConversationLockEntry] = {}
        self._locks_guard = asyncio.Lock()

    @asynccontextmanager
    async def _hold_conversation_lock(
        self,
        conversation_id: str,
    ) -> AsyncIterator[None]:
        """串行处理同一会话，并在无人使用后释放锁缓存。"""
        async with self._locks_guard:
            entry = self._conversation_locks.get(conversation_id)
            if entry is None:
                entry = _ConversationLockEntry(lock=asyncio.Lock())
                self._conversation_locks[conversation_id] = entry
            entry.references += 1

        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            async with self._locks_guard:
                entry.references -= 1
                if (
                    entry.references == 0
                    and self._conversation_locks.get(conversation_id) is entry
                ):
                    del self._conversation_locks[conversation_id]

    @staticmethod
    def _normalize_required(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} 不能为空")
        return normalized

    @staticmethod
    def _message_content(message: BaseMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        return str(message.content)

    @staticmethod
    def _config(conversation_id: str) -> dict:
        return {"configurable": {"thread_id": conversation_id}}

    @staticmethod
    def _normalize_request_id(request_id: str) -> str:
        normalized = ChatService._normalize_required(request_id, "request_id")
        if len(normalized) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", normalized):
            raise ValueError(
                "request_id 只能包含字母、数字、点、下划线、冒号和短横线，"
                "且长度不能超过 128"
            )
        return normalized

    async def _require_active_user(self, user_id: str) -> UserProfile | None:
        # 单元测试和显式注入的轻量用法可以不提供用户仓库；正式 Runtime
        # 始终注入 MySQLUserRepository，并在写入 PostgreSQL 会话前校验。
        if self.user_repository is None:
            return None
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise UserAccessError("当前用户不存在")
        if not user.is_active:
            raise UserAccessError("当前用户已停用")
        return user

    @staticmethod
    def _merge_tags(*tag_groups: Sequence[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for tags in tag_groups:
            for tag in tags:
                normalized = tag.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
        return merged

    async def chat(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message: str,
        request_id: str | None = None,
        user_name: str | None = None,
        user_gender: Literal["male", "female"] | None = None,
        user_tags: Sequence[str] | None = None,
    ) -> ChatResponse:
        normalized_user_id = self._normalize_required(user_id, "user_id")
        normalized_conversation_id = self._normalize_required(
            conversation_id,
            "conversation_id",
        )
        normalized_message = self._normalize_required(message, "message")
        normalized_request_id = (
            self._normalize_request_id(request_id)
            if request_id is not None
            else uuid4().hex
        )
        request_context = create_request_context(
            request_id=normalized_request_id,
            user_id=normalized_user_id,
            conversation_id=normalized_conversation_id,
        )
        monitoring_callback = AgentMonitoringCallback(request_context)

        with bind_request_context(request_context):
            started_at = log_request_started(request_context)
            try:
                user = await self._require_active_user(normalized_user_id)
                async with self._hold_conversation_lock(
                    normalized_conversation_id
                ):
                    await self.conversation_repository.ensure_owned(
                        normalized_conversation_id,
                        normalized_user_id,
                    )

                    graph_input: dict[str, Any] = {
                        # 只提交本轮的新消息；历史由 Checkpointer 按 thread_id 恢复。
                        "messages": [
                            HumanMessage(
                                content=normalized_message,
                                id=normalized_request_id,
                            )
                        ],
                        "user_id": normalized_user_id,
                        # 路由字段只描述当前一轮，不沿用上轮结果。
                        "current_intent": None,
                        "support_intent": None,
                        "refund_status": None,
                        "refund_ticket_id": None,
                        "refund_thread_id": None,
                        "conversation_id": normalized_conversation_id,
                        "rag_query": None,
                        "rewrite_test": 0,
                        "rag_support_state": None,
                        "rag_retrieve_docs": [],
                        "rag_grade": None,
                        "rag_retrieve_error": None
                    }
                    resolved_user_name = (
                        user_name.strip() or None
                        if user_name is not None
                        else user.user_name if user is not None else None
                    )
                    resolved_user_gender = (
                        user_gender
                        if user_gender is not None
                        else (
                            user.gender
                            if user is not None
                            and user.gender in {"male", "female"}
                            else None
                        )
                    )
                    resolved_tags = self._merge_tags(
                        user.tags if user is not None else [],
                        user_tags or [],
                    )
                    if resolved_user_name is not None:
                        graph_input["user_name"] = resolved_user_name
                    if resolved_user_gender is not None:
                        graph_input["user_gender"] = resolved_user_gender
                    if resolved_tags:
                        graph_input["user_tags"] = resolved_tags

                    config = self._config(normalized_conversation_id)
                    config["callbacks"] = [monitoring_callback]
                    state = await self.graph.ainvoke(
                        graph_input,
                        config=config,
                    )
                    messages = state.get("messages", [])
                    if not messages:
                        raise RuntimeError("智能体执行完成，但没有返回消息")

                    latest_message = messages[-1]
                    response = ChatResponse(
                        request_id=normalized_request_id,
                        conversation_id=normalized_conversation_id,
                        user_id=normalized_user_id,
                        content=self._message_content(latest_message),
                        message_id=getattr(latest_message, "id", None),
                    )
            except BaseException as exc:
                log_request_finished(request_context, started_at, error=exc)
                raise
            else:
                log_request_finished(request_context, started_at)
                return response

    async def get_state(self, *, user_id: str, conversation_id: str) -> dict:
        """读取会话最新状态；未来可用于会话详情接口和诊断。"""
        normalized_user_id = self._normalize_required(user_id, "user_id")
        normalized_conversation_id = self._normalize_required(
            conversation_id,
            "conversation_id",
        )
        await self._require_active_user(normalized_user_id)
        conversation = await self.conversation_repository.get_owned(
            normalized_conversation_id,
            normalized_user_id,
        )
        if conversation is None:
            raise ConversationNotFoundError("会话不存在")
        snapshot = await self.graph.aget_state(
            self._config(normalized_conversation_id)
        )
        return dict(snapshot.values)

    async def list_conversations(
        self,
        *,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        normalized_user_id = self._normalize_required(user_id, "user_id")
        await self._require_active_user(normalized_user_id)
        return await self.conversation_repository.list_by_user(
            normalized_user_id,
            limit=limit,
            offset=offset,
        )

    async def delete_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        normalized_user_id = self._normalize_required(user_id, "user_id")
        normalized_conversation_id = self._normalize_required(
            conversation_id,
            "conversation_id",
        )
        await self._require_active_user(normalized_user_id)
        async with self._hold_conversation_lock(normalized_conversation_id):
            conversation = await self.conversation_repository.get_owned(
                normalized_conversation_id,
                normalized_user_id,
            )
            if conversation is None:
                raise ConversationNotFoundError("会话不存在")
            checkpointer = getattr(self.graph, "checkpointer", None)
            if checkpointer is None or not hasattr(checkpointer, "adelete_thread"):
                raise RuntimeError("当前 Checkpointer 不支持删除会话")
            await checkpointer.adelete_thread(normalized_conversation_id)
            return await self.conversation_repository.delete_owned(
                normalized_conversation_id,
                normalized_user_id,
            )
