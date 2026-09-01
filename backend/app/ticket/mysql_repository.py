from typing import Any,Mapping
from uuid import uuid4

from app.ticket.models import Ticket

from sqlalchemy import text


class MySQLTicketRepository:

    def __init__(self, engine: Any, *, owns_engine: bool = False):
        self.engine = engine
        self._owns_engine = owns_engine

    @staticmethod
    def _to_ticket(row: Mapping[str, Any]) -> Ticket:
        return Ticket(
            ticket_id=str(row["ticket_id"]),
            user_id=str(row["user_id"]),
            ticket_type=str(row["ticket_type"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            latest_note=str(row.get("latest_note") or ""),
            subject=str(row.get("subject") or ""),
            description=str(row.get("description") or ""),
        )

    async def list_by_user(self, user_id: str) -> list[Ticket]:

        query = text(
            """
            SELECT
                ticket_id,
                user_id,
                ticket_type,
                status,
                created_at,
                latest_note,
                subject,
                description
            FROM support_tickets
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"user_id": user_id})
            return [self._to_ticket(row) for row in result.mappings().all()]

    async def get_by_id(self, ticket_id: str, user_id: str) -> Ticket | None:

        query = text(
            """
            SELECT
                ticket_id,
                user_id,
                ticket_type,
                status,
                created_at,
                latest_note,
                subject,
                description
            FROM support_tickets
            WHERE ticket_id = :ticket_id AND user_id = :user_id
            LIMIT 1
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(
                query,
                {"ticket_id": ticket_id.strip(), "user_id": user_id},
            )
            row = result.mappings().first()
            return self._to_ticket(row) if row else None

    async def create(
        self,
        user_id: str,
        subject: str,
        description: str,
    ) -> Ticket:

        ticket_id = f"TK-{uuid4().hex.upper()}"
        ticket_type = "support"
        status = "pending"
        latest_note = "已创建，等待人工客服处理"

        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO support_tickets (
                        ticket_id,
                        user_id,
                        ticket_type,
                        status,
                        subject,
                        description,
                        latest_note
                    ) VALUES (
                        :ticket_id,
                        :user_id,
                        :ticket_type,
                        :status,
                        :subject,
                        :description,
                        :latest_note
                    )
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "ticket_type": ticket_type,
                    "status": status,
                    "subject": subject,
                    "description": description,
                    "latest_note": latest_note,
                },
            )
            result = await connection.execute(
                text(
                    """
                    SELECT
                        ticket_id,
                        user_id,
                        ticket_type,
                        status,
                        created_at,
                        latest_note,
                        subject,
                        description
                    FROM support_tickets
                    WHERE ticket_id = :ticket_id
                      AND user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id, "user_id": user_id},
            )
            row = result.mappings().first()

        if row is None:
            raise RuntimeError("MySQL 创建工单后未返回记录")
        return self._to_ticket(row)

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()
