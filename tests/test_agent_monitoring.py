import asyncio
import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.checkpoint.memory import InMemorySaver


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.agent_config.graph import build_graph
import app.agent.nodes.supervisor_node as supervisor_module
import app.agent.nodes.support_classifier_node as classifier_module
import app.agent.nodes.support_node as support_module
from app.chat.service import ChatService
from app.conversation.in_memory_repository import InMemoryConversationRepository
from app.middleware.agent_monitoring import AgentMonitoringCallback
from app.middleware.context import (
    bind_request_context,
    create_request_context,
    get_request_context,
)
from tests.fakes.business_repositories import build_graph_with_fakes


class ToolAwareFakeMessagesListChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class ContextRecordingGraph:
    def __init__(self):
        self.records: dict[str, tuple[str | None, str | None]] = {}

    async def ainvoke(self, graph_input, config=None):
        text = graph_input["messages"][0].content
        before = get_request_context()
        await asyncio.sleep(0.01)
        after = get_request_context()
        self.records[text] = (
            before.request_id if before else None,
            after.request_id if after else None,
        )
        return {"messages": [AIMessage(content=f"reply:{text}")]}


class FailingGraph:
    async def ainvoke(self, graph_input, config=None):
        raise RuntimeError("private failure detail password=secret")


class AgentMonitoringCallbackTests(unittest.TestCase):
    def test_context_hashes_identifiers_and_resets_after_request(self):
        context = create_request_context(
            request_id="request-1",
            user_id="raw-user-id",
            conversation_id="raw-conversation-id",
        )
        self.assertNotEqual(context.user_ref, "raw-user-id")
        self.assertNotEqual(context.conversation_ref, "raw-conversation-id")
        self.assertIsNone(get_request_context())

        with bind_request_context(context):
            self.assertEqual(get_request_context(), context)

        self.assertIsNone(get_request_context())

    def test_model_logs_usage_without_message_content(self):
        context = create_request_context(
            request_id="request-model",
            user_id="private-user",
            conversation_id="private-conversation",
        )
        callback = AgentMonitoringCallback(context)
        run_id = uuid4()
        response = LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="private model answer",
                            usage_metadata={
                                "input_tokens": 12,
                                "output_tokens": 5,
                                "total_tokens": 17,
                            },
                        )
                    )
                ]
            ]
        )

        with self.assertLogs("agent_monitoring", level="INFO") as captured:
            callback.on_chat_model_start(
                {"name": "fake-model"},
                [[HumanMessage(content="private prompt body")]],
                run_id=run_id,
            )
            callback.on_llm_end(response, run_id=run_id)

        logs = "\n".join(captured.output)
        self.assertIn("event=model_started", logs)
        self.assertIn("model=fake-model", logs)
        self.assertIn("input_tokens=12", logs)
        self.assertIn("output_tokens=5", logs)
        self.assertNotIn("private prompt body", logs)
        self.assertNotIn("private model answer", logs)
        self.assertNotIn("private-user", logs)
        self.assertNotIn("private-conversation", logs)

    def test_tool_logs_only_argument_names_and_error_type(self):
        context = create_request_context(
            request_id="request-tool-error",
            user_id="user-secret",
            conversation_id="conversation-secret",
        )
        callback = AgentMonitoringCallback(context)
        run_id = uuid4()

        with self.assertLogs("agent_monitoring", level="INFO") as captured:
            callback.on_tool_start(
                {"name": "query_ticket"},
                '{"ticket_id":"TK-PRIVATE"}',
                run_id=run_id,
                inputs={"ticket_id": "TK-PRIVATE"},
            )
            callback.on_tool_error(
                RuntimeError("database password=top-secret"),
                run_id=run_id,
            )

        logs = "\n".join(captured.output)
        self.assertIn("tool=query_ticket", logs)
        self.assertIn('arg_fields=["ticket_id"]', logs)
        self.assertIn("error_type=RuntimeError", logs)
        self.assertNotIn("TK-PRIVATE", logs)
        self.assertNotIn("top-secret", logs)
        self.assertNotIn("user-secret", logs)
        self.assertNotIn("conversation-secret", logs)


class AgentMonitoringIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    def setUp(self):
        self.original_supervisor_llm = supervisor_module.llm
        self.original_classifier_llm = classifier_module.llm
        self.original_support_llm = support_module.llm

    def tearDown(self):
        supervisor_module.llm = self.original_supervisor_llm
        classifier_module.llm = self.original_classifier_llm
        support_module.llm = self.original_support_llm

    async def test_toolnode_events_inherit_request_callback(self):
        supervisor_module.llm = FakeListChatModel(responses=["support"])
        classifier_module.llm = FakeListChatModel(responses=["general"])
        support_module.llm = ToolAwareFakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "query_ticket",
                            "args": {"ticket_id": "TK-10001"},
                            "id": "call-monitor-ticket",
                        }
                    ],
                ),
                AIMessage(content="工单查询完成。"),
            ]
        )
        service = ChatService(
            build_graph_with_fakes(
                build_graph,
                checkpointer=InMemorySaver(),
            ),
            InMemoryConversationRepository(),
        )

        with self.assertLogs("agent_monitoring", level="INFO") as captured:
            response = await service.chat(
                user_id="cli-user",
                conversation_id="monitor-tool-conversation",
                request_id="request-tool-integration",
                message="秘密查询 TK-10001",
            )

        logs = "\n".join(captured.output)
        self.assertEqual(response.request_id, "request-tool-integration")
        self.assertEqual(response.content, "工单查询完成。")
        self.assertIn("event=tool_started", logs)
        self.assertIn("event=tool_finished", logs)
        self.assertIn("tool=query_ticket", logs)
        self.assertIn('arg_fields=["ticket_id"]', logs)
        self.assertNotIn("TK-10001", logs)
        self.assertNotIn("秘密查询", logs)
        self.assertNotIn("cli-user", logs)
        self.assertNotIn("monitor-tool-conversation", logs)

    async def test_concurrent_requests_keep_separate_context(self):
        graph = ContextRecordingGraph()
        service = ChatService(graph, InMemoryConversationRepository())

        with self.assertLogs("agent_monitoring", level="INFO"):
            first, second = await asyncio.gather(
                service.chat(
                    user_id="user-a",
                    conversation_id="conversation-a",
                    request_id="request-a",
                    message="message-a",
                ),
                service.chat(
                    user_id="user-b",
                    conversation_id="conversation-b",
                    request_id="request-b",
                    message="message-b",
                ),
            )

        self.assertEqual(first.request_id, "request-a")
        self.assertEqual(second.request_id, "request-b")
        self.assertEqual(graph.records["message-a"], ("request-a", "request-a"))
        self.assertEqual(graph.records["message-b"], ("request-b", "request-b"))
        self.assertIsNone(get_request_context())

    async def test_request_error_log_omits_exception_message(self):
        service = ChatService(FailingGraph(), InMemoryConversationRepository())

        with self.assertLogs("agent_monitoring", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                await service.chat(
                    user_id="private-user",
                    conversation_id="private-conversation",
                    request_id="request-error",
                    message="private message body",
                )

        logs = "\n".join(captured.output)
        self.assertIn("event=request_finished", logs)
        self.assertIn("status=error", logs)
        self.assertIn("error_type=RuntimeError", logs)
        self.assertNotIn("private failure detail", logs)
        self.assertNotIn("password=secret", logs)
        self.assertNotIn("private message body", logs)
        self.assertNotIn("private-user", logs)
        self.assertNotIn("private-conversation", logs)

    async def test_invalid_request_id_is_rejected_before_logging(self):
        service = ChatService(ContextRecordingGraph(), InMemoryConversationRepository())
        with self.assertRaises(ValueError):
            await service.chat(
                user_id="user",
                conversation_id="conversation",
                request_id="bad\nrequest",
                message="hello",
            )


if __name__ == "__main__":
    unittest.main()
