from app.product.repository import ProductRepository
from app.utils.logger_handler import get_logger


logger = get_logger("product_service")


class ProductService:
    """向销售工具提供稳定、安全的商品查询返回结构。"""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def search_products(
        self,
        query: str = "",
        category: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 5,
    ) -> dict:
        if min_price is not None and min_price < 0:
            return self._invalid_price_range()
        if max_price is not None and max_price < 0:
            return self._invalid_price_range()
        if min_price is not None and max_price is not None and min_price > max_price:
            return self._invalid_price_range()

        safe_limit = min(max(limit, 1), 20)
        try:
            products = await self.repository.search(
                query=query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=safe_limit,
            )
        except Exception as exc:
            logger.error(
                "搜索商品失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "PRODUCT_BACKEND_ERROR",
                "message": "商品系统暂时不可用",
            }

        return {
            "ok": True,
            "count": len(products),
            "products": [product.to_search_dict() for product in products],
        }

    async def get_product_details(self, product_id: str) -> dict:
        product_or_error = await self._get_product(product_id)
        if isinstance(product_or_error, dict):
            return product_or_error
        return {
            "ok": True,
            "found": True,
            "product": product_or_error.to_detail_dict(),
        }

    async def check_inventory(self, product_id: str) -> dict:
        product_or_error = await self._get_product(product_id)
        if isinstance(product_or_error, dict):
            return product_or_error
        return {
            "ok": True,
            "found": True,
            "inventory": {
                "product_id": product_or_error.product_id,
                "name": product_or_error.name,
                "available": product_or_error.stock > 0,
                "stock": product_or_error.stock,
            },
        }

    async def get_current_promotions(self, product_id: str) -> dict:
        product_or_error = await self._get_product(product_id)
        if isinstance(product_or_error, dict):
            return product_or_error
        return {
            "ok": True,
            "found": True,
            "promotion": {
                "product_id": product_or_error.product_id,
                "name": product_or_error.name,
                "current_price": product_or_error.price,
                "promotions": product_or_error.promotions,
            },
        }

    async def _get_product(self, product_id: str):
        normalized_id = product_id.strip().upper()
        if not normalized_id:
            return {
                "ok": False,
                "error_code": "INVALID_PRODUCT_ID",
                "message": "请提供有效的商品编号",
            }
        try:
            product = await self.repository.get_by_id(normalized_id)
        except Exception as exc:
            logger.error(
                "查询商品详情失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "PRODUCT_BACKEND_ERROR",
                "message": "商品系统暂时不可用",
            }
        if product is None:
            return {"ok": True, "found": False, "product": None}
        return product

    @staticmethod
    def _invalid_price_range() -> dict:
        return {
            "ok": False,
            "error_code": "INVALID_PRICE_RANGE",
            "message": "价格区间无效",
        }
