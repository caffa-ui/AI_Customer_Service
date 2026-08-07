from langchain_core.messages import AIMessage
from app.agent.State.state import SCRMState

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