from typing import Protocol, runtime_checkable

from app.ticket.models import Ticket


@runtime_checkable
class TicketRepository(Protocol):

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

    async def create_refund(
        self,
        user_id: str,
        order_id: str,
        subject: str,
        description: str,
        conversation_id: str,
        refund_thread_id: str,
    ) -> Ticket:
        ...

    async def find_pending_refund(
        self,
        user_id: str,
        order_id: str,
    ) -> Ticket | None:
        ...

    async def list_refunds(self, status: str | None = None) -> list[Ticket]:
        ...

    async def review_refund(
        self,
        ticket_id: str,
        reviewer_id: str,
        decision: str,
        review_note: str,
    ) -> Ticket | None:
        ...

    async def close(self) -> None:
        ...
