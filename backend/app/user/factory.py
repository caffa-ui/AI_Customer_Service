from typing import Any

from app.database.mysql import create_mysql_engine
from app.user.mysql_repository import MySQLUserRepository
from app.user.repository import UserRepository


def create_user_repository(mysql_engine: Any | None = None) -> UserRepository:
    engine = mysql_engine or create_mysql_engine()
    return MySQLUserRepository(engine, owns_engine=mysql_engine is None)
