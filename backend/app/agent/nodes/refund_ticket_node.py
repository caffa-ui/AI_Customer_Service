import re

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.State.state import SCRMState
from app.ticket.service import TicketService
from app.order.service import OrderService

def create_refund_ticket_node(ticket_service: TicketService, order_service: OrderService, refund_graph):

    async def node(state: SCRMState):
        conversation_id = state.get("conversation_id") or "unknown"
        latest = next(
            (m.content for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            "",
        )
        order_match = re.search(r"\bORD-[A-Za-z0-9_-]+\b", latest, re.IGNORECASE)
        order_id = order_match.group(0).upper() if order_match else ""
        refund_thread_id = f"refund-{conversation_id}-{state.get('user_id')}"

        if order_id:
            order_result = await order_service.query_order(order_id, state.get("user_id", ""))
            if not order_result.get("ok") or not order_result.get("found"):
                return {
                    "messages": [AIMessage(content=f"没有找到属于您的订单 {order_id}，请核对订单号后再申请退款。")],
                    "refund_status": None,
                }
            result = await ticket_service.create_refund_ticket(
                user_id=state.get("user_id", ""),
                order_id=order_id,
                subject="用户申请退款",
                description=latest,
                conversation_id=conversation_id,
                refund_thread_id=refund_thread_id,
            )
            ticket = result.get("ticket") if result.get("ok") else None
            ticket_id = ticket.get("ticket_id") if ticket else None
            if ticket_id:
                refund_thread_id = ticket.get("refund_thread_id") or refund_thread_id
                await refund_graph.ainvoke(
                    {"ticket_id": ticket_id, "user_id": state.get("user_id", ""), "order_id": order_id},
                    config={"configurable": {"thread_id": refund_thread_id}},
                )
                return {
                    "messages": [AIMessage(content=f"您的退款申请已提交人工审核，工单号为 {ticket_id}，审核期间您仍可以继续咨询其他问题。")],
                    "refund_status": "pending",
                    "refund_ticket_id": ticket_id,
                    "refund_thread_id": refund_thread_id,
                }
        return {
            "messages": [AIMessage(content="请提供需要退款的订单号（例如 ORD-20260801），我会为您提交人工审核。")],
            "refund_status": "pending",
        }
    return node

