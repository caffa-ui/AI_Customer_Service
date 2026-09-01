from typing import Any

from app.database.mysql import create_mysql_engine
from app.order.mysql_repository import MySQLOrderRepository
from app.order.repository import OrderRepository


def create_order_repository(mysql_engine: Any | None = None) -> OrderRepository:
    """创建生产订单的数据库MySQL"""
    engine = mysql_engine or create_mysql_engine()
    return MySQLOrderRepository(
        engine,
        owns_engine=mysql_engine is None,
    )
