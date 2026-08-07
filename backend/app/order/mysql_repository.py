from datetime import date, datetime
from typing import Any

from app.order.models import Order, OrderItem


class MySQLOrderRepository:
    def __init__(self, engine: Any, *, owns_engine: bool = False):
        self.engine = engine
        self._owns_engine = owns_engine

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    async def get_by_id(self, order_id: str, user_id: str) -> Order | None:
        from sqlalchemy import text

        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        order_id,
                        user_id,
                        status,
                        created_at,
                        total_amount,
                        carrier,
                        tracking_number,
                        logistics_status,
                        latest_logistics,
                        estimated_delivery
                    FROM orders
                    WHERE order_id = :order_id
                      AND user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"order_id": order_id, "user_id": user_id},
            )
            row = result.mappings().first()
            if row is None:
                return None

            item_result = await connection.execute(
                text(
                    """
                    SELECT product_id, product_name, quantity, unit_price
                    FROM order_items
                    WHERE order_id = :order_id
                    ORDER BY order_item_id
                    """
                ),
                {"order_id": order_id},
            )
            items = [
                OrderItem(
                    product_id=str(item["product_id"]),
                    name=str(item["product_name"]),
                    quantity=int(item["quantity"]),
                    unit_price=float(item["unit_price"]),
                )
                for item in item_result.mappings().all()
            ]

        return Order(
            order_id=str(row["order_id"]),
            user_id=str(row["user_id"]),
            status=str(row["status"]),
            created_at=self._string(row["created_at"]),
            total_amount=float(row["total_amount"]),
            items=items,
            carrier=str(row.get("carrier") or ""),
            tracking_number=str(row.get("tracking_number") or ""),
            logistics_status=str(row.get("logistics_status") or ""),
            latest_logistics=str(row.get("latest_logistics") or ""),
            estimated_delivery=self._string(row.get("estimated_delivery")),
        )

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()
