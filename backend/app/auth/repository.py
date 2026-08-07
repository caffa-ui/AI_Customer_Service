from datetime import datetime
from typing import Protocol, runtime_checkable

from app.auth.models import UserCredential


@runtime_checkable
class AuthRepository(Protocol):
    async def verify_schema(self) -> None:
        ...

    async def get_credential(self, user_id: str) -> UserCredential | None:
        ...

    async def update_password_hash(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> None:
        ...

    async def replace_password_and_revoke_sessions(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> bool:
        ...

    async def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        ...

    async def rotate_refresh_session(
        self,
        current_token_id: str,
        new_token_id: str,
        user_id: str,
        new_expires_at: datetime,
    ) -> bool:
        ...

    async def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        ...
