from typing import Any

from app.user.models import UserProfile


class MySQLUserRepository:
    def __init__(self, engine: Any, *, owns_engine: bool = False):
        self.engine = engine
        self._owns_engine = owns_engine

    async def get_by_id(self, user_id: str) -> UserProfile | None:
        from sqlalchemy import text

        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT user_id, user_name, gender, status
                    FROM users
                    WHERE user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            row = result.mappings().first()
            if row is None:
                return None

            tag_result = await connection.execute(
                text(
                    """
                    SELECT tag
                    FROM user_tags
                    WHERE user_id = :user_id
                    ORDER BY tag
                    """
                ),
                {"user_id": user_id},
            )
            tags = [str(tag) for tag in tag_result.scalars().all()]

        return UserProfile(
            user_id=str(row["user_id"]),
            user_name=str(row["user_name"]) if row["user_name"] else None,
            gender=str(row["gender"]) if row["gender"] else None,
            status=str(row["status"]),
            tags=tags,
        )

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()
