import re

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.State.state import SCRMState
from app.ticket.service import TicketService


def create_refund_ticket_node(ticket_service: TicketService, order_service, refund_graph):
    async def node(state: SCRMState):
        conversation_id = state.get("conversation_id") or "unknown"
        latest = next(
            (m.content for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            "",
        )
        order_match = re.search(r"\bORD-[A-Za-z0-9_-]+\b", latest, re.IGNORECASE)
        order_id = order_match.group(0).upper() if order_match else ""
        refund_thread_id = f"refund-{conversation_id}-{state.get('user_id', '')}"
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

def refund_ticket_node(state: SCRMState):
    """
    负责生成退款工单，并安抚用户。
    在真实的业务中，你可以在这里执行 SQL/API 操作，把退款请求写入客服后台的待处理队列/数据库表。
    """
    # TODO: 在此处写入你的 MySQL "待审批工单表"
    # insert_into_ticket_queue(user_id=state['user_id'], reason=...)

    print("[Refund Ticket] 正在将请求写入后台人工待处理队列...")

    msg = AIMessage(
        content="您的退款申请我们已经收到。我已为您生成加急退款工单，专属售后主管会在24小时内为您审核处理，请您耐心等待短信或微信通知。")

    return {
        "messages": [msg],
        "refund_status": "pending"  # 标记为待处理
    }


def human_review_node(state: SCRMState):
    """
    这是断点恢复后执行的节点。
    当人工在后台点击了“同意/拒绝”后，图会被唤醒并走到这里，负责给用户播报最终结果。
    """
    status = state.get("refund_status")
    if status == "approved":
        msg = AIMessage(content="【系统通知】您好，主管已通过您的退款申请，资金将按原路返回，请注意查收。")
    else:
        msg = AIMessage(content="【系统通知】抱歉，您的退款申请未通过审核。如有疑问，请回复转人工客服。")

    return {"messages": [msg]}
