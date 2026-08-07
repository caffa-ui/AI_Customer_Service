from typing import Protocol, runtime_checkable

from app.ticket.models import Ticket


@runtime_checkable
class TicketRepository(Protocol):
    """工单数据源协议，生产环境由 MySQL 实现。"""

    async def list_by_user(self, user_id: str) -> list[Ticket]:
        ...

    async def get_by_id(self, ticket_id: str, user_id: str) -> Ticket | None:
        ...

    async def create(
        self,
        user_id: str,
        subject: str,
        description: str,
    ) -> Ticket:
        ...

    async def close(self) -> None:
        ...
