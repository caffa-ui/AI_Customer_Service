from typing import Protocol, runtime_checkable

from app.order.models import Order


@runtime_checkable
class OrderRepository(Protocol):
    """订单数据源协议，所有实现必须按 user_id 做数据隔离。"""

    async def get_by_id(self, order_id: str, user_id: str) -> Order | None:
        ...

    async def close(self) -> None:
        ...
