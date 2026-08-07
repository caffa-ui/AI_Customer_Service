from typing import Any

from app.database.mysql import create_mysql_engine
from app.product.mysql_repository import MySQLProductRepository
from app.product.repository import ProductRepository


def create_product_repository(mysql_engine: Any | None = None) -> ProductRepository:
    """创建唯一的生产商品数据源：MySQL。"""
    engine = mysql_engine or create_mysql_engine()
    return MySQLProductRepository(
        engine,
        owns_engine=mysql_engine is None,
    )
