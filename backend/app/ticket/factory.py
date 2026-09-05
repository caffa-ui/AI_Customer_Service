from typing import Any

from app.database.mysql import create_mysql_engine
from app.ticket.mysql_repository import MySQLTicketRepository
from app.ticket.repository import TicketRepository


def create_ticket_repository(mysql_engine: Any | None = None) -> TicketRepository:
    """创建MySQL工单数据库"""
    engine = mysql_engine or create_mysql_engine()
    return MySQLTicketRepository(
        engine,
        owns_engine=mysql_engine is None
    )


# Backward-compatible private name used by older tests and integrations.
_create_mysql_repository = create_ticket_repository
