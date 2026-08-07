import json
import os
from typing import Any

from app.product.models import Product
from app.product.search import rank_products


class MySQLProductRepository:
    def __init__(self, engine: Any, *, owns_engine: bool = False):
        self.engine = engine
        self._owns_engine = owns_engine

    @staticmethod
    def _json_dict(value: Any) -> dict[str, str]:
        if value is None:
            return {}
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            raise ValueError("商品 specifications 必须是 JSON 对象")
        return {str(key): str(item) for key, item in parsed.items()}

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        if value is None:
            return []
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, list):
            raise ValueError("商品 keywords 必须是 JSON 数组")
        return [str(item) for item in parsed]

    @classmethod
    def _to_product(
        cls,
        row: Any,
        promotions: list[str] | None = None,
    ) -> Product:
        return Product(
            product_id=str(row["product_id"]),
            name=str(row["name"]),
            category=str(row["category"]),
            price=float(row["price"]),
            summary=str(row.get("summary") or ""),
            specifications=cls._json_dict(row.get("specifications")),
            keywords=cls._json_list(row.get("keywords")),
            stock=int(row.get("stock") or 0),
            promotions=promotions or [],
        )

    async def search(
        self,
        query: str = "",
        category: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 5,
    ) -> list[Product]:
        from sqlalchemy import text

        conditions = ["p.is_active = TRUE"]
        parameters: dict[str, Any] = {}
        if category.strip():
            conditions.append("p.category LIKE :category")
            parameters["category"] = f"%{category.strip()}%"
        if min_price is not None:
            conditions.append("p.price >= :min_price")
            parameters["min_price"] = min_price
        if max_price is not None:
            conditions.append("p.price <= :max_price")
            parameters["max_price"] = max_price

        raw_candidate_limit = (
            os.getenv("MYSQL_PRODUCT_CANDIDATE_LIMIT") or "1000"
        ).strip()
        try:
            candidate_limit = int(raw_candidate_limit)
        except ValueError as exc:
            raise RuntimeError("MYSQL_PRODUCT_CANDIDATE_LIMIT 必须是正整数") from exc
        if candidate_limit <= 0:
            raise RuntimeError("MYSQL_PRODUCT_CANDIDATE_LIMIT 必须是正整数")
        parameters["candidate_limit"] = candidate_limit

        statement = text(
            f"""
            SELECT
                p.product_id,
                p.name,
                p.category,
                p.price,
                p.summary,
                p.specifications,
                p.keywords,
                COALESCE(i.stock, 0) AS stock
            FROM products AS p
            LEFT JOIN product_inventory AS i
                ON i.product_id = p.product_id
            WHERE {' AND '.join(conditions)}
            ORDER BY p.product_id
            LIMIT :candidate_limit
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(statement, parameters)
            products = [
                self._to_product(row)
                for row in result.mappings().all()
            ]

        return rank_products(
            products,
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
        )

    async def get_by_id(self, product_id: str) -> Product | None:
        from sqlalchemy import text

        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        p.product_id,
                        p.name,
                        p.category,
                        p.price,
                        p.summary,
                        p.specifications,
                        p.keywords,
                        COALESCE(i.stock, 0) AS stock
                    FROM products AS p
                    LEFT JOIN product_inventory AS i
                        ON i.product_id = p.product_id
                    WHERE p.product_id = :product_id
                      AND p.is_active = TRUE
                    LIMIT 1
                    """
                ),
                {"product_id": product_id},
            )
            row = result.mappings().first()
            if row is None:
                return None

            promotion_result = await connection.execute(
                text(
                    """
                    SELECT description
                    FROM product_promotions
                    WHERE product_id = :product_id
                      AND is_active = TRUE
                      AND (start_at IS NULL OR start_at <= UTC_TIMESTAMP(6))
                      AND (end_at IS NULL OR end_at >= UTC_TIMESTAMP(6))
                    ORDER BY promotion_id
                    """
                ),
                {"product_id": product_id},
            )
            promotions = [
                str(description)
                for description in promotion_result.scalars().all()
            ]

        return self._to_product(row, promotions)

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()
