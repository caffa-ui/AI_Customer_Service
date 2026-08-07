from typing import Any

from app.database.mysql import create_mysql_engine
from app.ticket.mysql_repository import MySQLTicketRepository
from app.ticket.repository import TicketRepository


def create_ticket_repository(mysql_engine: Any | None = None) -> TicketRepository:
    """创建唯一的生产工单数据源：MySQL。"""
    return _create_mysql_repository(mysql_engine)


def _create_mysql_repository(
    mysql_engine: Any | None = None,
) -> MySQLTicketRepository:
    engine = mysql_engine or create_mysql_engine()
    return MySQLTicketRepository(
        engine,
        owns_engine=mysql_engine is None,
    )
