from pathlib import Path
import sys
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.tool.product_tools import create_product_tools
from app.product.service import ProductService
from tests.fakes.business_repositories import FakeProductRepository


class ProductServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = ProductService(FakeProductRepository())

    async def test_search_products_by_need_and_budget(self):
        result = await self.service.search_products(
            query="轻薄办公",
            max_price=6000,
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["products"][0]["product_id"], "P-1001")
        self.assertNotIn("stock", result["products"][0])

    async def test_details_inventory_and_promotions_are_separate(self):
        details = await self.service.get_product_details("p-1002")
        inventory = await self.service.check_inventory("P-2001")
        promotions = await self.service.get_current_promotions("P-1002")

        self.assertEqual(details["product"]["product_id"], "P-1002")
        self.assertFalse(inventory["inventory"]["available"])
        self.assertEqual(inventory["inventory"]["stock"], 0)
        self.assertGreater(len(promotions["promotion"]["promotions"]), 0)

    def test_product_tool_names_and_schema(self):
        tools = {tool.name: tool for tool in create_product_tools(self.service)}

        self.assertEqual(
            set(tools),
            {
                "search_products",
                "get_product_details",
                "check_inventory",
                "get_current_promotions",
            },
        )
        self.assertEqual(
            set(tools["get_product_details"].args),
            {"product_id"},
        )


if __name__ == "__main__":
    unittest.main()
