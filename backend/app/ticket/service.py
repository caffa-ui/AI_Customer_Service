from app.ticket.repository import TicketRepository
from app.utils.logger_handler import get_logger


logger = get_logger("ticket_service")


class TicketService:
    """在智能体工具与具体数据源之间提供稳定的业务返回结构。"""

    def __init__(self, repository: TicketRepository):
        self.repository = repository

    async def list_my_tickets(self, user_id: str) -> dict:
        if not user_id:
            return {
                "ok": False,
                "error_code": "UNAUTHENTICATED",
                "message": "无法确认当前用户身份",
            }

        try:
            tickets = await self.repository.list_by_user(user_id)
        except Exception as exc:
            logger.error(
                "查询工单列表失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "TICKET_BACKEND_ERROR",
                "message": "工单系统暂时不可用",
            }

        return {
            "ok": True,
            "count": len(tickets),
            "tickets": [ticket.to_public_dict() for ticket in tickets],
        }

    async def query_ticket(self, ticket_id: str, user_id: str) -> dict:
        normalized_id = ticket_id.strip().upper()
        if not normalized_id:
            return {
                "ok": False,
                "error_code": "INVALID_TICKET_ID",
                "message": "请提供有效的工单号",
            }
        if not user_id:
            return {
                "ok": False,
                "error_code": "UNAUTHENTICATED",
                "message": "无法确认当前用户身份",
            }

        try:
            ticket = await self.repository.get_by_id(normalized_id, user_id)
        except Exception as exc:
            logger.error(
                "查询工单详情失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "TICKET_BACKEND_ERROR",
                "message": "工单系统暂时不可用",
            }

        if ticket is None:
            return {"ok": True, "found": False, "ticket": None}

        return {"ok": True, "found": True, "ticket": ticket.to_public_dict()}

    async def create_support_ticket(
        self,
        subject: str,
        description: str,
        user_id: str,
    ) -> dict:
        normalized_subject = subject.strip()
        normalized_description = description.strip()
        if not user_id:
            return {
                "ok": False,
                "error_code": "UNAUTHENTICATED",
                "message": "无法确认当前用户身份",
            }
        if not normalized_subject or not normalized_description:
            return {
                "ok": False,
                "error_code": "INVALID_TICKET_CONTENT",
                "message": "工单主题和问题描述不能为空",
            }
        if len(normalized_subject) > 100 or len(normalized_description) > 1000:
            return {
                "ok": False,
                "error_code": "TICKET_CONTENT_TOO_LONG",
                "message": "工单主题或问题描述过长",
            }

        try:
            ticket = await self.repository.create(
                user_id=user_id,
                subject=normalized_subject,
                description=normalized_description,
            )
        except Exception as exc:
            logger.error(
                "创建售后工单失败: "
                f"error_type={type(exc).__name__}"
            )
            return {
                "ok": False,
                "error_code": "TICKET_BACKEND_ERROR",
                "message": "工单系统暂时不可用",
            }

        return {
            "ok": True,
            "created": True,
            "persistence": getattr(
                self.repository,
                "persistence_mode",
                "repository",
            ),
            "ticket": ticket.to_public_dict(),
        }
