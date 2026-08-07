import os

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _positive_int_env(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须是正整数")
    return value


def _non_negative_int_env(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是非负整数") from exc
    if value < 0:
        raise RuntimeError(f"{name} 必须是非负整数")
    return value


def required_mysql_dsn() -> str:
    dsn = (os.getenv("MYSQL_DSN") or "").strip()
    if not dsn:
        raise RuntimeError("MySQL 配置缺失: MYSQL_DSN")

    try:
        url = make_url(dsn)
    except Exception as exc:
        raise RuntimeError("MYSQL_DSN 格式无效") from exc
    if url.drivername != "mysql+asyncmy":
        raise RuntimeError("MYSQL_DSN 必须使用 mysql+asyncmy:// 协议")
    if not url.username or not url.host or not url.database:
        raise RuntimeError("MYSQL_DSN 必须包含用户名、主机和数据库名")
    return dsn


def create_mysql_engine() -> AsyncEngine:
    """创建可由 CLI/FastAPI 生命周期共享的异步 MySQL Engine。"""
    dsn = required_mysql_dsn()
    pool_size = _positive_int_env("MYSQL_POOL_SIZE", 5)
    max_overflow = _non_negative_int_env("MYSQL_MAX_OVERFLOW", 10)
    pool_recycle = _positive_int_env("MYSQL_POOL_RECYCLE_SECONDS", 1800)
    pool_timeout = _positive_int_env("MYSQL_POOL_TIMEOUT_SECONDS", 30)
    connect_timeout = _positive_int_env("MYSQL_CONNECT_TIMEOUT_SECONDS", 10)
    read_timeout = _positive_int_env("MYSQL_READ_TIMEOUT_SECONDS", 30)

    return create_async_engine(
        dsn,
        pool_pre_ping=True,
        pool_recycle=pool_recycle,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=float(pool_timeout),
        connect_args={
            "connect_timeout": connect_timeout,
            "read_timeout": read_timeout,
            "init_command": "SET time_zone = '+00:00'",
        },
    )


async def verify_mysql_connection(engine: AsyncEngine) -> str:
    """启动阶段验证连接，并返回实际数据库名。"""
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT 1 AS ok, DATABASE() AS database_name")
                )
            ).mappings().one()
    except Exception as exc:
        raise RuntimeError(
            "无法连接 MySQL，请检查 MYSQL_DSN、数据库状态和网络权限"
        ) from exc

    if row["ok"] != 1 or not row["database_name"]:
        raise RuntimeError("MySQL 连接检查未返回有效数据库")
    return str(row["database_name"])
