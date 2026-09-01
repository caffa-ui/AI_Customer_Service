from pathlib import Path
import sys
import unittest

from langchain_core.documents import Document

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.tool.agentic_rag_tool import create_knowledge_tools
from app.agent.tool.support_tools import create_order_tools
from app.knowledge.rag_repository import RagKnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.order.service import OrderService
from tests.fakes.business_repositories import FakeOrderRepository


class FakeVectorStoreService:
    def __init__(self):
        self.load_count = 0
        self.search_count = 0
        self.closed = False

    def load_documents(self):
        self.load_count += 1
        return {"loaded_files": 1, "skipped_files": 0, "total_files": 1}

    def similarity_search(self, query: str, limit: int):
        self.search_count += 1
        return [
            (
                Document(
                    page_content="删除旧配对记录后重新搜索，仍失败时重置耳机。",
                    metadata={
                        "source": "C:/knowledge/support_knowledge.txt",
                        "source_name": "support_knowledge.txt",
                        "chunk_index": 0,
                    },
                ),
                0.91,
            )
        ][:limit]

    def close(self):
        self.closed = True


class SupportServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.order_service = OrderService(FakeOrderRepository())
        self.fake_vector_store = FakeVectorStoreService()
        self.rag_repository = RagKnowledgeRepository(
            vector_store_factory=lambda: self.fake_vector_store
        )
        self.knowledge_service = KnowledgeService(self.rag_repository)

    async def test_order_and_logistics_hide_user_id(self):
        order = await self.order_service.query_order("ord-20260801", "cli-user")
        logistics = await self.order_service.check_logistics(
            "ORD-20260801",
            "cli-user",
        )

        self.assertTrue(order["found"])
        self.assertNotIn("user_id", order["order"])
        self.assertEqual(logistics["logistics"]["tracking_number"], "SF1234567890")

    async def test_order_query_is_isolated_by_user(self):
        result = await self.order_service.query_order(
            "ORD-PRIVATE-01",
            "cli-user",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["found"])

    async def test_rag_knowledge_search(self):
        result = await self.knowledge_service.search_support_knowledge(
            "蓝牙耳机连接不上"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["articles"][0]["source_type"], "rag")
        self.assertEqual(
            result["articles"][0]["title"],
            "support_knowledge.txt",
        )
        self.assertEqual(self.fake_vector_store.load_count, 1)

        await self.knowledge_service.search_support_knowledge("再次查询")
        self.assertEqual(self.fake_vector_store.load_count, 1)

    def test_support_tool_schema_hides_user_id(self):
        order_tools = {
            tool.name: tool for tool in create_order_tools(self.order_service)
        }
        knowledge_tools = create_knowledge_tools(self.knowledge_service)

        self.assertEqual(set(order_tools["query_order"].args), {"order_id"})
        self.assertEqual(set(order_tools["check_logistics"].args), {"order_id"})
        self.assertEqual(knowledge_tools[0].name, "search_support_knowledge")


if __name__ == "__main__":
    unittest.main()
