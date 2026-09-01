import asyncio
from pathlib import Path
import os
import sys
import unittest

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.agent_config.graph import build_graph
import app.agent.nodes.supervisor_and_chat_node as supervisor_module
from app.chat.service import ChatService
from app.conversation.in_memory_repository import InMemoryConversationRepository
from app.conversation.repository import (
    ConversationAccessError,
    ConversationNotFoundError,
)
from app.user.models import UserProfile
from app.user.repository import UserAccessError
from tests.fakes.business_repositories import build_graph_with_fakes


class FakeUserRepository:
    def __init__(self, users: dict[str, UserProfile]):
        self.users = users

    async def get_by_id(self, user_id: str) -> UserProfile | None:
        return self.users.get(user_id)

    async def close(self) -> None:
        return None


class ConcurrencyTrackingGraph:
    def __init__(self):
        self.active_calls = 0
        self.max_active_calls = 0

    async def ainvoke(self, graph_input, config=None):
        self.active_calls += 1
        self.max_active_calls = max(
            self.max_active_calls,
            self.active_calls,
        )
        try:
            await asyncio.sleep(0.01)
            return {"messages": [AIMessage(content="ok")]}
        finally:
            self.active_calls -= 1


class PersistentChatServiceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    def setUp(self):
        self.original_supervisor_llm = supervisor_module.llm

    def tearDown(self):
        supervisor_module.llm = self.original_supervisor_llm

    @staticmethod
    def create_service(
        checkpointer,
        repository,
        user_repository=None,
    ) -> ChatService:
        return ChatService(
            build_graph_with_fakes(
                build_graph,
                checkpointer=checkpointer,
            ),
            repository,
            user_repository,
        )

    async def test_mysql_user_profile_is_loaded_into_graph_state(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        user_repository = FakeUserRepository(
            {
                "user-1": UserProfile(
                    user_id="user-1",
                    user_name="数据库用户",
                    gender="female",
                    status="active",
                    tags=["办公", "轻薄"],
                )
            }
        )
        supervisor_module.llm = FakeListChatModel(
            responses=["chat", "画像已加载"]
        )
        service = self.create_service(
            checkpointer,
            repository,
            user_repository,
        )

        response = await service.chat(
            user_id="user-1",
            conversation_id="profile-conversation",
            message="你好",
        )
        state = await service.get_state(
            user_id="user-1",
            conversation_id="profile-conversation",
        )

        self.assertEqual(response.content, "画像已加载")
        self.assertEqual(state["user_name"], "数据库用户")
        self.assertEqual(state["user_gender"], "female")
        self.assertIn("办公", state["user_tags"])
        self.assertIn("轻薄", state["user_tags"])

    async def test_unknown_mysql_user_is_rejected_before_conversation_creation(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        service = self.create_service(
            checkpointer,
            repository,
            FakeUserRepository({}),
        )

        with self.assertRaises(UserAccessError):
            await service.chat(
                user_id="missing-user",
                conversation_id="must-not-be-created",
                message="你好",
            )

        self.assertNotIn("must-not-be-created", repository._conversations)

    async def test_inactive_mysql_user_is_rejected(self):
        user_repository = FakeUserRepository(
            {
                "disabled-user": UserProfile(
                    user_id="disabled-user",
                    status="disabled",
                )
            }
        )
        service = self.create_service(
            InMemorySaver(),
            InMemoryConversationRepository(),
            user_repository,
        )

        with self.assertRaises(UserAccessError):
            await service.chat(
                user_id="disabled-user",
                conversation_id="disabled-conversation",
                message="你好",
            )

    async def test_same_conversation_recovers_state_after_service_rebuild(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        supervisor_module.llm = FakeListChatModel(
            responses=["chat", "第一轮答复", "chat", "第二轮答复"]
        )

        first_service = self.create_service(checkpointer, repository)
        first_response = await first_service.chat(
            user_id="user-1",
            conversation_id="conversation-1",
            message="我喜欢蓝牙耳机",
            user_name="小林",
            user_tags=["耳机"],
        )
        self.assertEqual(first_response.content, "第一轮答复")

        await first_service.graph.aupdate_state(
            {"configurable": {"thread_id": "conversation-1"}},
            {"summary": "用户明确偏好蓝牙耳机。"},
        )

        # 重建 graph 和 ChatService，验证新服务实例会从同一 Checkpointer 恢复状态。
        second_service = self.create_service(checkpointer, repository)
        second_response = await second_service.chat(
            user_id="user-1",
            conversation_id="conversation-1",
            message="你还记得我的偏好吗？",
        )
        self.assertEqual(second_response.content, "第二轮答复")

        state = await second_service.get_state(
            user_id="user-1",
            conversation_id="conversation-1",
        )
        human_messages = [
            message
            for message in state["messages"]
            if isinstance(message, HumanMessage)
        ]
        self.assertEqual(
            [message.content for message in human_messages],
            ["我喜欢蓝牙耳机", "你还记得我的偏好吗？"],
        )
        self.assertEqual(state["user_name"], "小林")
        self.assertIn("耳机", state["user_tags"])
        self.assertEqual(state["summary"], "用户明确偏好蓝牙耳机。")

    async def test_different_conversations_do_not_share_messages(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        supervisor_module.llm = FakeListChatModel(
            responses=["chat", "会话 A", "chat", "会话 B"]
        )
        service = self.create_service(checkpointer, repository)

        await service.chat(
            user_id="user-1",
            conversation_id="conversation-a",
            message="这是 A 的消息",
        )
        await service.chat(
            user_id="user-1",
            conversation_id="conversation-b",
            message="这是 B 的消息",
        )

        state_a = await service.get_state(
            user_id="user-1",
            conversation_id="conversation-a",
        )
        state_b = await service.get_state(
            user_id="user-1",
            conversation_id="conversation-b",
        )
        text_a = "\n".join(str(message.content) for message in state_a["messages"])
        text_b = "\n".join(str(message.content) for message in state_b["messages"])
        self.assertIn("这是 A 的消息", text_a)
        self.assertNotIn("这是 B 的消息", text_a)
        self.assertIn("这是 B 的消息", text_b)
        self.assertNotIn("这是 A 的消息", text_b)

    async def test_conversation_cannot_be_accessed_by_another_user(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        supervisor_module.llm = FakeListChatModel(responses=["chat", "已创建"])
        service = self.create_service(checkpointer, repository)

        await service.chat(
            user_id="owner",
            conversation_id="private-conversation",
            message="这是私有会话",
        )

        with self.assertRaises(ConversationAccessError):
            await service.get_state(
                user_id="another-user",
                conversation_id="private-conversation",
            )

    async def test_same_conversation_is_serialized_and_lock_is_released(self):
        graph = ConcurrencyTrackingGraph()
        service = ChatService(graph, InMemoryConversationRepository())

        await asyncio.gather(
            service.chat(
                user_id="user-1",
                conversation_id="shared-conversation",
                request_id="request-1",
                message="第一条消息",
            ),
            service.chat(
                user_id="user-1",
                conversation_id="shared-conversation",
                request_id="request-2",
                message="第二条消息",
            ),
        )

        self.assertEqual(graph.max_active_calls, 1)
        self.assertEqual(service._conversation_locks, {})

    async def test_list_and_delete_conversation_include_checkpoint(self):
        checkpointer = InMemorySaver()
        repository = InMemoryConversationRepository()
        supervisor_module.llm = FakeListChatModel(responses=["chat", "已创建"])
        service = self.create_service(checkpointer, repository)

        await service.chat(
            user_id="user-1",
            conversation_id="conversation-delete",
            message="稍后删除",
        )
        conversations = await service.list_conversations(user_id="user-1")
        self.assertEqual(
            [item.conversation_id for item in conversations],
            ["conversation-delete"],
        )

        deleted = await service.delete_conversation(
            user_id="user-1",
            conversation_id="conversation-delete",
        )
        self.assertTrue(deleted)
        self.assertEqual(await service.list_conversations(user_id="user-1"), [])
        with self.assertRaises(ConversationNotFoundError):
            await service.get_state(
                user_id="user-1",
                conversation_id="conversation-delete",
            )
        checkpoint = await checkpointer.aget(
            {"configurable": {"thread_id": "conversation-delete"}}
        )
        self.assertIsNone(checkpoint)


if __name__ == "__main__":
    unittest.main()
