from pathlib import Path
import sys
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.tool.ticket_tools import create_ticket_tools
from app.ticket.service import TicketService
from tests.fakes.business_repositories import FakeTicketRepository


class TicketServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = FakeTicketRepository()
        self.service = TicketService(self.repository)

    async def test_list_only_returns_current_users_tickets(self):
        result = await self.service.list_my_tickets("cli-user")

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        self.assertNotIn("user_id", result["tickets"][0])

    async def test_query_ticket_returns_ticket_details(self):
        result = await self.service.query_ticket("tk-10001", "cli-user")

        self.assertTrue(result["found"])
        self.assertEqual(result["ticket"]["ticket_id"], "TK-10001")

    async def test_query_does_not_expose_another_users_ticket(self):
        result = await self.service.query_ticket("TK-10003", "cli-user")

        self.assertTrue(result["ok"])
        self.assertFalse(result["found"])

    async def test_created_ticket_is_available_in_current_repository(self):
        created = await self.service.create_support_ticket(
            "笔记本无法开机",
            "已经充电并长按电源键，仍然没有反应。",
            "cli-user",
        )

        self.assertTrue(created["created"])
        self.assertEqual(created["persistence"], "test_memory")
        self.assertNotIn("user_id", created["ticket"])

        queried = await self.service.query_ticket(
            created["ticket"]["ticket_id"],
            "cli-user",
        )
        self.assertTrue(queried["found"])
        self.assertEqual(queried["ticket"]["subject"], "笔记本无法开机")

    def test_tool_schema_hides_user_id(self):
        tools = {tool.name: tool for tool in create_ticket_tools(self.service)}

        self.assertEqual(tools["list_my_tickets"].args, {})
        self.assertEqual(set(tools["query_ticket"].args), {"ticket_id"})
        self.assertEqual(
            set(tools["create_support_ticket"].args),
            {"subject", "description"},
        )


if __name__ == "__main__":
    unittest.main()
