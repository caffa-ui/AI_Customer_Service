from typing import Protocol, runtime_checkable

from app.product.models import Product


@runtime_checkable
class ProductRepository(Protocol):
    """
    这是专门定义的抽象的接口，用于后面接入你们数据库，我这里后面接入的是Mysql
    一定要是函数名相同，参数可以不同
    这里强烈建议使用前去了解Protocol和@runtime_checkable
    """

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
