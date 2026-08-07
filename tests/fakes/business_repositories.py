import json
import re
from datetime import datetime
from pathlib import Path

from app.knowledge.models import KnowledgeArticle
from app.order.models import Order
from app.product.models import Product
from app.product.search import rank_products
from app.ticket.models import Ticket


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture(filename: str) -> list[dict]:
    data = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"测试 fixture 的根节点必须是列表: {filename}")
    return data


class FakeProductRepository:
    """基于测试 fixture 的商品仓储，不属于应用运行时。"""

    def __init__(self):
        self._products = [
            Product.model_validate(item)
            for item in _load_fixture("products.json")
        ]

    async def search(
        self,
        query: str = "",
        category: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 5,
    ) -> list[Product]:
        return rank_products(
            self._products,
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
        )

    async def get_by_id(self, product_id: str) -> Product | None:
        normalized_id = product_id.strip().upper()
        return next(
            (
                product
                for product in self._products
                if product.product_id.upper() == normalized_id
            ),
            None,
        )

    async def close(self) -> None:
        return None


class FakeOrderRepository:
    """基于测试 fixture 的订单仓储。"""

    def __init__(self):
        self._orders = [
            Order.model_validate(item)
            for item in _load_fixture("orders.json")
        ]

    async def get_by_id(self, order_id: str, user_id: str) -> Order | None:
        normalized_id = order_id.strip().upper()
        return next(
            (
                order
                for order in self._orders
                if order.order_id.upper() == normalized_id
                and order.user_id == user_id
            ),
            None,
        )

    async def close(self) -> None:
        return None


class FakeTicketRepository:
    """基于测试 fixture 的进程内工单仓储。"""

    persistence_mode = "test_memory"

    def __init__(self):
        self._tickets = [
            Ticket.model_validate(item)
            for item in _load_fixture("tickets.json")
        ]
        existing_numbers = [
            int(match.group(1))
            for ticket in self._tickets
            if (match := re.fullmatch(r"TK-(\d+)", ticket.ticket_id.upper()))
        ]
        self._next_ticket_number = max(existing_numbers, default=10000) + 1

    async def list_by_user(self, user_id: str) -> list[Ticket]:
        return [ticket for ticket in self._tickets if ticket.user_id == user_id]

    async def get_by_id(self, ticket_id: str, user_id: str) -> Ticket | None:
        normalized_id = ticket_id.strip().upper()
        return next(
            (
                ticket
                for ticket in self._tickets
                if ticket.ticket_id.upper() == normalized_id
                and ticket.user_id == user_id
            ),
            None,
        )

    async def create(
        self,
        user_id: str,
        subject: str,
        description: str,
    ) -> Ticket:
        ticket = Ticket(
            ticket_id=f"TK-{self._next_ticket_number:05d}",
            user_id=user_id,
            ticket_type="support",
            status="open",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            latest_note="已创建，等待人工客服处理",
            subject=subject,
            description=description,
        )
        self._next_ticket_number += 1
        self._tickets.append(ticket)
        return ticket

    async def close(self) -> None:
        return None


class FakeKnowledgeRepository:
    """图路由测试使用的最小知识仓储，避免访问嵌入服务。"""

    async def search(
        self,
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> list[KnowledgeArticle]:
        return [
            KnowledgeArticle(
                article_id="test-support-1",
                title="测试售后知识",
                category=category or "售后",
                content="这是仅供自动化测试使用的售后知识。",
                source_type="test_fake",
            )
        ][:limit]

    async def close(self) -> None:
        return None


def build_graph_with_fakes(build_graph, *, checkpointer=None):
    """为图测试显式注入全部业务 Fake Repository。"""
    return build_graph(
        ticket_repository=FakeTicketRepository(),
        product_repository=FakeProductRepository(),
        order_repository=FakeOrderRepository(),
        knowledge_repository=FakeKnowledgeRepository(),
        checkpointer=checkpointer,
    )
