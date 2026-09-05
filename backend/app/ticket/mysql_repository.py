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
            order_id=(str(row["order_id"]) if row.get("order_id") else None),
            conversation_id=(
                str(row["conversation_id"]) if row.get("conversation_id") else None
            ),
            refund_thread_id=(
                str(row["refund_thread_id"])
                if row.get("refund_thread_id")
                else None
            ),
            reviewer_id=(str(row["reviewer_id"]) if row.get("reviewer_id") else None),
            review_note=(str(row["review_note"]) if row.get("review_note") else None),
            reviewed_at=(str(row["reviewed_at"]) if row.get("reviewed_at") else None),
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
                description, order_id, conversation_id, refund_thread_id,
                reviewer_id, review_note, reviewed_at
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
                description, order_id, conversation_id, refund_thread_id,
                reviewer_id, review_note, reviewed_at
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
                        description, order_id, conversation_id, refund_thread_id,
                        reviewer_id, review_note, reviewed_at
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

    async def find_pending_refund(self, user_id: str, order_id: str) -> Ticket | None:
        query = text(
            """
            SELECT ticket_id, user_id, ticket_type, status, created_at,
                   latest_note, subject, description, order_id, conversation_id,
                   refund_thread_id, reviewer_id, review_note, reviewed_at
            FROM support_tickets
            WHERE user_id = :user_id AND order_id = :order_id
              AND ticket_type = 'refund' AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"user_id": user_id, "order_id": order_id})
            row = result.mappings().first()
        return self._to_ticket(row) if row else None

    async def list_refunds(self, status: str | None = None) -> list[Ticket]:
        query = text(
            """
            SELECT ticket_id, user_id, ticket_type, status, created_at,
                   latest_note, subject, description, order_id, conversation_id,
                   refund_thread_id, reviewer_id, review_note, reviewed_at
            FROM support_tickets
            WHERE ticket_type = 'refund' AND (:status IS NULL OR status = :status)
            ORDER BY created_at DESC LIMIT 100
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"status": status})
            return [self._to_ticket(row) for row in result.mappings().all()]

    async def create_refund(
        self,
        user_id: str,
        order_id: str,
        subject: str,
        description: str,
        conversation_id: str,
        refund_thread_id: str,
    ) -> Ticket:
        existing = await self.find_pending_refund(user_id, order_id)
        if existing is not None:
            return existing
        ticket_id = f"TK-{uuid4().hex.upper()}"
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO support_tickets (
                        ticket_id, user_id, order_id, ticket_type, status,
                        subject, description, latest_note, conversation_id,
                        refund_thread_id
                    ) VALUES (
                        :ticket_id, :user_id, :order_id, 'refund', 'pending',
                        :subject, :description, :latest_note, :conversation_id,
                        :refund_thread_id
                    )
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "order_id": order_id,
                    "subject": subject,
                    "description": description,
                    "latest_note": "已提交，等待人工退款审核",
                    "conversation_id": conversation_id,
                    "refund_thread_id": refund_thread_id,
                },
            )
            result = await connection.execute(
                text(
                    """
                    SELECT ticket_id, user_id, ticket_type, status, created_at,
                           latest_note, subject, description, order_id,
                           conversation_id, refund_thread_id, reviewer_id,
                           review_note, reviewed_at
                    FROM support_tickets
                    WHERE ticket_id = :ticket_id AND user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id, "user_id": user_id},
            )
            row = result.mappings().first()
        if row is None:
            raise RuntimeError("MySQL 创建退款工单后未返回记录")
        return self._to_ticket(row)

    async def review_refund(
        self,
        ticket_id: str,
        reviewer_id: str,
        decision: str,
        review_note: str,
    ) -> Ticket | None:
        status = "approved" if decision == "approved" else "rejected"
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE support_tickets
                    SET status = :status,
                        latest_note = :latest_note,
                        reviewer_id = :reviewer_id,
                        review_note = :review_note,
                        reviewed_at = CURRENT_TIMESTAMP(6)
                    WHERE ticket_id = :ticket_id
                      AND ticket_type = 'refund'
                      AND status = 'pending'
                    """
                ),
                {
                    "status": status,
                    "latest_note": review_note,
                    "reviewer_id": reviewer_id,
                    "review_note": review_note,
                    "ticket_id": ticket_id,
                },
            )
            result = await connection.execute(
                text(
                    """
                    SELECT ticket_id, user_id, ticket_type, status, created_at,
                           latest_note, subject, description, order_id,
                           conversation_id, refund_thread_id, reviewer_id,
                           review_note, reviewed_at
                    FROM support_tickets
                    WHERE ticket_id = :ticket_id
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id},
            )
            row = result.mappings().first()
        return self._to_ticket(row) if row else None

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()
