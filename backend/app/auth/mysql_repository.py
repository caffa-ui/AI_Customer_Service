from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.auth.models import UserCredential


class MySQLAuthRepository:
    def __init__(self, engine: Any):
        self.engine = engine

    async def verify_schema(self) -> None:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(
                    text("SELECT 1 FROM user_credentials LIMIT 1")
                )
                await connection.execute(
                    text("SELECT 1 FROM auth_refresh_tokens LIMIT 1")
                )
        except Exception as exc:
            raise RuntimeError(
                "MySQL 认证表不可用，请先执行 backend/sql/mysql/003_auth.sql"
            ) from exc

    async def get_credential(self, user_id: str) -> UserCredential | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT c.user_id, c.password_hash, u.status
                    FROM user_credentials AS c
                    INNER JOIN users AS u ON u.user_id = c.user_id
                    WHERE c.user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return UserCredential(
            user_id=str(row["user_id"]),
            password_hash=str(row["password_hash"]),
            is_active=str(row["status"]) == "active",
        )

    async def update_password_hash(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE user_credentials
                    SET password_hash = :new_hash,
                        password_changed_at = CURRENT_TIMESTAMP(6)
                    WHERE user_id = :user_id
                      AND password_hash = :old_hash
                    """
                ),
                {
                    "user_id": user_id,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                },
            )

    async def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO auth_refresh_tokens (
                        token_id,
                        user_id,
                        expires_at
                    ) VALUES (
                        :token_id,
                        :user_id,
                        :expires_at
                    )
                    """
                ),
                {
                    "token_id": token_id,
                    "user_id": user_id,
                    "expires_at": expires_at,
                },
            )

    async def replace_password_and_revoke_sessions(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> bool:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE user_credentials
                    SET password_hash = :new_hash,
                        password_changed_at = UTC_TIMESTAMP(6)
                    WHERE user_id = :user_id
                      AND password_hash = :old_hash
                    """
                ),
                {
                    "user_id": user_id,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                },
            )
            if not result.rowcount:
                return False
            await connection.execute(
                text(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = UTC_TIMESTAMP(6)
                    WHERE user_id = :user_id AND revoked_at IS NULL
                    """
                ),
                {"user_id": user_id},
            )
        return True

    async def rotate_refresh_session(
        self,
        current_token_id: str,
        new_token_id: str,
        user_id: str,
        new_expires_at: datetime,
    ) -> bool:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT token_id
                    FROM auth_refresh_tokens
                    WHERE token_id = :token_id
                      AND user_id = :user_id
                      AND revoked_at IS NULL
                      AND expires_at > UTC_TIMESTAMP(6)
                    FOR UPDATE
                    """
                ),
                {"token_id": current_token_id, "user_id": user_id},
            )
            if result.first() is None:
                return False

            await connection.execute(
                text(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = UTC_TIMESTAMP(6),
                        replaced_by_token_id = :new_token_id
                    WHERE token_id = :token_id
                    """
                ),
                {
                    "token_id": current_token_id,
                    "new_token_id": new_token_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO auth_refresh_tokens (
                        token_id,
                        user_id,
                        expires_at
                    ) VALUES (
                        :token_id,
                        :user_id,
                        :expires_at
                    )
                    """
                ),
                {
                    "token_id": new_token_id,
                    "user_id": user_id,
                    "expires_at": new_expires_at,
                },
            )
        return True

    async def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = UTC_TIMESTAMP(6)
                    WHERE token_id = :token_id
                      AND user_id = :user_id
                      AND revoked_at IS NULL
                    """
                ),
                {"token_id": token_id, "user_id": user_id},
            )
        return bool(result.rowcount)
