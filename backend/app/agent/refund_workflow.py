from typing import TypedDict

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class RefundReviewState(TypedDict, total=False):
    ticket_id: str
    user_id: str
    order_id: str
    refund_status: str
    review_note: str
    messages: list


def refund_review_node(state: RefundReviewState):
    """暂停在人工审核点；恢复时接收管理员的 decision/review_note。"""
    review = interrupt(
        {
            "type": "refund_review",
            "ticket_id": state["ticket_id"],
            "user_id": state["user_id"],
            "order_id": state.get("order_id"),
        }
    )
    decision = review.get("decision") if isinstance(review, dict) else None
    status = "approved" if decision == "approved" else "rejected"
    note = str(review.get("review_note") or "") if isinstance(review, dict) else ""
    return {
        "refund_status": status,
        "review_note": note,
        "messages": [
            AIMessage(
                content=(
                    "您的退款申请已通过人工审核，模拟退款已处理。"
                    if status == "approved"
                    else f"您的退款申请未通过人工审核。原因：{note or '请联系人工客服'}"
                )
            )
        ],
    }


def build_refund_review_graph(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(RefundReviewState)
    builder.add_node("refund_review", refund_review_node)
    builder.add_edge(START, "refund_review")
    builder.add_edge("refund_review", END)
    return builder.compile(checkpointer=checkpointer)
