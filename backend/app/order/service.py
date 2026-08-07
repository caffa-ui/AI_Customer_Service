from app.order.repository import OrderRepository
from app.utils.logger_handler import get_logger


logger = get_logger("order_service")


class OrderService:
    """向售后工具提供带用户隔离的订单与物流查询。"""

    def __init__(self, repository: OrderRepository):
        self.repository = repository

    async def query_order(self, order_id: str, user_id: str) -> dict:
        order_or_error = await self._get_order(order_id, user_id)
        if isinstance(order_or_error, dict):
            return order_or_error
        return {
            "ok": True,
            "found": True,
            "order": order_or_error.to_public_dict(),
        }

    async def check_logistics(self, order_id: str, user_id: str) -> dict:
        order_or_error = await self._get_order(order_id, user_id)
        if isinstance(order_or_error, dict):
            return order_or_error
        return {
            "ok": True,
            "found": True,
            "logistics": order_or_error.to_logistics_dict(),
        }

    async def _get_order(self, order_id: str, user_id: str):
        normalized_id = order_id.strip().upper()
        if not normalized_id:
            return {
                "ok": False,
                "error_code": "INVALID_ORDER_ID",
                "message": "请提供有效的订单号",
            }
        if not user_id:
            return {
                "ok": False,
                "error_code": "UNAUTHENTICATED",
                "message": "无法确认当前用户身份",
            }
        try:
            order = await self.repository.get_by_id(normalized_id, user_id)
        except Exception as exc:
            logger.error(
                "查询订单或物流失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "ORDER_BACKEND_ERROR",
                "message": "订单系统暂时不可用",
            }
        if order is None:
            return {"ok": True, "found": False, "order": None}
        return order
