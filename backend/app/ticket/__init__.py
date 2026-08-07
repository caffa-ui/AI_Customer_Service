"""工单领域模块。"""

from app.ticket.factory import create_ticket_repository
from app.ticket.models import Ticket
from app.ticket.repository import TicketRepository
from app.ticket.service import TicketService

__all__ = [
    "Ticket",
    "TicketRepository",
    "TicketService",
    "create_ticket_repository",
]
