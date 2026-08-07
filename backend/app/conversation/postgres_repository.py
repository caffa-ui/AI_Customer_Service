from typing import Any

from app.conversation.models import Conversation
from app.conversation.repository import ConversationAccessError


class PostgresConversationRepository:
    """使用 PostgreSQL 保存 conversation_id 与 user_id 的归属关系。"""

    def __init__(self, pool: Any):
        self.pool = pool

    async def setup(self) -> None:
        """幂等创建会话元数据表和用户查询索引。"""
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_conversations_user_updated
                ON agent_conversations (user_id, updated_at DESC)
                """
            )

    @staticmethod
    def _to_conversation(row: Any) -> Conversation:
        return Conversation(
            conversation_id=str(row["conversation_id"]),
            user_id=str(row["user_id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def ensure_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                # 先原子创建，再加行锁读取。这样多个 FastAPI 实例首次收到
                # 同一 conversation_id 时也不会发生“先查询、后重复插入”的竞态。
                await connection.execute(
                    """
                    INSERT INTO agent_conversations (conversation_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (conversation_id) DO NOTHING
                    """,
                    (conversation_id, user_id),
                )
                cursor = await connection.execute(
                    """
                    SELECT conversation_id, user_id, created_at, updated_at
                    FROM agent_conversations
                    WHERE conversation_id = %s
                    FOR UPDATE
                    """,
                    (conversation_id,),
                )
                row = await cursor.fetchone()

                if row is None:
                    raise RuntimeError("PostgreSQL 未返回会话记录")
                if str(row["user_id"]) != user_id:
                    raise ConversationAccessError("当前用户无权访问该会话")

                cursor = await connection.execute(
                    """
                    UPDATE agent_conversations
                    SET updated_at = NOW()
                    WHERE conversation_id = %s
                    RETURNING conversation_id, user_id, created_at, updated_at
                    """,
                    (conversation_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            raise RuntimeError("PostgreSQL 未返回会话记录")
        return self._to_conversation(row)

    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[Conversation]:
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT conversation_id, user_id, created_at, updated_at
                FROM agent_conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return [self._to_conversation(row) for row in rows]

    async def get_owned(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation | None:
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT conversation_id, user_id, created_at, updated_at
                FROM agent_conversations
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        if str(row["user_id"]) != user_id:
            raise ConversationAccessError("当前用户无权访问该会话")
        return self._to_conversation(row)

    async def delete_owned(self, conversation_id: str, user_id: str) -> bool:
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM agent_conversations
                WHERE conversation_id = %s AND user_id = %s
                RETURNING conversation_id
                """,
                (conversation_id, user_id),
            )
            deleted = await cursor.fetchone()
            if deleted is not None:
                return True

            cursor = await connection.execute(
                """
                SELECT user_id
                FROM agent_conversations
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            existing = await cursor.fetchone()
        if existing is not None:
            raise ConversationAccessError("当前用户无权访问该会话")
        return False
