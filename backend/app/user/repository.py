from typing import Protocol, runtime_checkable

from app.user.models import UserProfile


class UserAccessError(PermissionError):
    """用户不存在或已停用，不能创建或访问智能体会话。"""


@runtime_checkable
class UserRepository(Protocol):
    async def get_by_id(self, user_id: str) -> UserProfile | None:
        ...

    async def close(self) -> None:
        ...
