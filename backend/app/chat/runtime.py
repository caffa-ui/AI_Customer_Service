import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.agent_config.graph import build_graph
from app.auth.config import AuthSettings
from app.auth.mysql_repository import MySQLAuthRepository
from app.auth.service import AuthService
from app.chat.service import ChatService
from app.conversation.postgres_repository import PostgresConversationRepository
from app.database.mysql import create_mysql_engine, verify_mysql_connection
from app.knowledge.factory import create_knowledge_repository
from app.order.factory import create_order_repository
from app.product.factory import create_product_repository
from app.ticket.factory import create_ticket_repository
from app.user.factory import create_user_repository
from app.utils.logger_handler import get_logger


ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)
logger = get_logger("chat_runtime")


@dataclass(frozen=True, slots=True)
class RuntimeServices:
    chat_service: ChatService
    auth_service: AuthService | None = None


def _required_postgres_dsn() -> str:
    dsn = (os.getenv("POSTGRES_DSN") or "").strip()
    if not dsn:
        raise RuntimeError(
            "持久会话需要 PostgreSQL：请在 backend/.env 中配置 POSTGRES_DSN"
        )
    return dsn


def _positive_int_env(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须是正整数")
    return value


@asynccontextmanager
async def _create_services(
    *,
    include_auth: bool,
) -> AsyncIterator[RuntimeServices]:
    dsn = _required_postgres_dsn()
    min_size = _positive_int_env("POSTGRES_POOL_MIN_SIZE", 1)
    max_size = _positive_int_env("POSTGRES_POOL_MAX_SIZE", 10)
    timeout = _positive_int_env("POSTGRES_POOL_TIMEOUT_SECONDS", 30)
    if min_size > max_size:
        raise RuntimeError("POSTGRES_POOL_MIN_SIZE 不能大于 POSTGRES_POOL_MAX_SIZE")

    pool = AsyncConnectionPool(
        conninfo=dsn,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        min_size=min_size,
        max_size=max_size,
        timeout=float(timeout),
        open=False,
        name="scrm-agent-postgres",
    )
    repositories = []
    mysql_engine = None

    try:
        try:
            await pool.open(wait=True, timeout=float(timeout))
        except Exception as exc:
            raise RuntimeError(
                "无法连接 PostgreSQL，请检查 POSTGRES_DSN、数据库状态和网络权限"
            ) from exc

        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()

        conversation_repository = PostgresConversationRepository(pool)
        await conversation_repository.setup()

        mysql_engine = create_mysql_engine()
        mysql_database = await verify_mysql_connection(mysql_engine)
        logger.info(f"MySQL 业务数据源已连接: database={mysql_database}")

        user_repository = create_user_repository(mysql_engine)
        auth_service = None
        if include_auth:
            auth_repository = MySQLAuthRepository(mysql_engine)
            await auth_repository.verify_schema()
            auth_service = AuthService(
                auth_repository,
                AuthSettings.from_env(),
            )
        ticket_repository = create_ticket_repository(mysql_engine)
        product_repository = create_product_repository(mysql_engine)
        order_repository = create_order_repository(mysql_engine)
        knowledge_repository = create_knowledge_repository()
        repositories = [
            user_repository,
            ticket_repository,
            product_repository,
            order_repository,
            knowledge_repository,
        ]

        graph = build_graph(
            ticket_repository=ticket_repository,
            product_repository=product_repository,
            order_repository=order_repository,
            knowledge_repository=knowledge_repository,
            checkpointer=checkpointer,
        )
        yield RuntimeServices(
            chat_service=ChatService(
                graph,
                conversation_repository,
                user_repository,
            ),
            auth_service=auth_service,
        )
    finally:
        for repository in repositories:
            try:
                await repository.close()
            except Exception as exc:
                logger.error(
                    "关闭业务 Repository 失败: "
                    f"error_type={type(exc).__name__}"
                )
        if mysql_engine is not None:
            await mysql_engine.dispose()
        await pool.close()


@asynccontextmanager
async def create_runtime_services() -> AsyncIterator[RuntimeServices]:
    """创建 FastAPI 共享的认证与聊天服务。"""
    async with _create_services(include_auth=True) as services:
        if services.auth_service is None:
            raise RuntimeError("认证服务初始化失败")
        yield services


@asynccontextmanager
async def create_chat_service() -> AsyncIterator[ChatService]:
    """保留 CLI 使用的聊天服务生命周期入口。"""
    async with _create_services(include_auth=False) as services:
        yield services.chat_service


# 保留旧名称，避免已有 CLI 或外部调用方立即失效。
create_postgres_chat_service = create_chat_service

