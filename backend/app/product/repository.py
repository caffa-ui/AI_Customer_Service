from typing import Protocol, runtime_checkable

from app.product.models import Product


@runtime_checkable
class ProductRepository(Protocol):
    """商品数据源协议，后续可由 MySQL 或商品 API 实现。"""

    async def search(
        self,
        query: str = "",
        category: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 5,
    ) -> list[Product]:
        ...

    async def get_by_id(self, product_id: str) -> Product | None:
        ...

    async def close(self) -> None:
        ...
