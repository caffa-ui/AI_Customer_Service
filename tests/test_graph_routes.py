import os
from pathlib import Path
import sys
import unittest

from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.agent_config.graph import build_graph
import app.agent.nodes.sale_node as sale_module
import app.agent.nodes.supervisor_node as supervisor_module
import app.agent.nodes.support_classifier_node as classifier_module
import app.agent.nodes.support_node as support_module
from tests.fakes.business_repositories import build_graph_with_fakes

graph = build_graph_with_fakes(build_graph)


class ToolAwareFakeListChatModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class ToolAwareFakeMessagesListChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class GraphRouteTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # 测试只验证本地路由，不上报 LangSmith 轨迹。
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    @staticmethod
    def state(text: str, user_id: str = "test-user") -> dict:
        return {
            "messages": [HumanMessage(content=text)],
            "user_id": user_id,
            "user_name": None,
            "user_gender": None,
            "user_tags": [],
            "summary": "",
        }

    async def test_sale_route(self):
        supervisor_module.llm = FakeListChatModel(responses=["sale"])
        sale_module.llm = ToolAwareFakeListChatModel(responses=["sale-ok"])

        result = await graph.ainvoke(self.state("请推荐一件商品"))

        self.assertEqual(result["current_intent"], "sale")
        self.assertEqual(result["messages"][-1].content, "sale-ok")

    async def test_product_tool_loop(self):
        supervisor_module.llm = FakeListChatModel(responses=["sale"])
        sale_module.llm = ToolAwareFakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_products",
                            "args": {"query": "轻薄办公", "max_price": 6000},
                            "id": "call-search-products",
                        }
                    ],
                ),
                AIMessage(content="为您找到轻薄商务本 Air 14。"),
            ]
        )

        result = await graph.ainvoke(self.state("推荐六千以内的轻薄办公本"))

        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("P-1001", tool_messages[0].content)
        self.assertEqual(result["messages"][-1].content, "为您找到轻薄商务本 Air 14。")

    async def test_chat_route(self):
        supervisor_module.llm = FakeListChatModel(responses=["chat", "chat-ok"])

        result = await graph.ainvoke(self.state("你好"))

        self.assertEqual(result["current_intent"], "chat")
        self.assertEqual(result["messages"][-1].content, "chat-ok")

    async def test_general_support_route(self):
        supervisor_module.llm = FakeListChatModel(responses=["support"])
        classifier_module.llm = FakeListChatModel(responses=["general"])
        support_module.llm = ToolAwareFakeListChatModel(responses=["support-ok"])

        result = await graph.ainvoke(self.state("请查询物流"))

        self.assertEqual(result["support_intent"], "general")
        self.assertEqual(result["messages"][-1].content, "support-ok")

    async def test_refund_route(self):
        supervisor_module.llm = FakeListChatModel(responses=["support"])
        classifier_module.llm = FakeListChatModel(responses=["refund"])

        result = await graph.ainvoke(self.state("我要申请退款"))

        self.assertEqual(result["support_intent"], "refund")
        self.assertEqual(result["refund_status"], "pending")

    async def test_ticket_tool_loop(self):
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
                            "id": "call-query-ticket",
                        }
                    ],
                ),
                AIMessage(content="工单 TK-10001 正在等待售后主管审核。"),
            ]
        )

        result = await graph.ainvoke(
            self.state("帮我查一下 TK-10001", user_id="cli-user")
        )

        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("TK-10001", tool_messages[0].content)
        self.assertEqual(
            result["messages"][-1].content,
            "工单 TK-10001 正在等待售后主管审核。",
        )

    async def test_order_tool_loop(self):
        supervisor_module.llm = FakeListChatModel(responses=["support"])
        classifier_module.llm = FakeListChatModel(responses=["general"])
        support_module.llm = ToolAwareFakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "check_logistics",
                            "args": {"order_id": "ORD-20260801"},
                            "id": "call-check-logistics",
                        }
                    ],
                ),
                AIMessage(content="订单正在运输中。"),
            ]
        )

        result = await graph.ainvoke(
            self.state("查询 ORD-20260801 的物流", user_id="cli-user")
        )

        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("SF1234567890", tool_messages[0].content)
        self.assertEqual(result["messages"][-1].content, "订单正在运输中。")

    async def test_list_my_tickets_tool_loop(self):
        supervisor_module.llm = FakeListChatModel(responses=["support"])
        classifier_module.llm = FakeListChatModel(responses=["general"])
        support_module.llm = ToolAwareFakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_my_tickets",
                            "args": {},
                            "id": "call-list-tickets",
                        }
                    ],
                ),
                AIMessage(content="您当前有 2 条工单。"),
            ]
        )

        result = await graph.ainvoke(
            self.state("查询一下我的工单", user_id="cli-user")
        )

        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn('"count": 2', tool_messages[0].content)
        self.assertEqual(result["messages"][-1].content, "您当前有 2 条工单。")


if __name__ == "__main__":
    unittest.main()
