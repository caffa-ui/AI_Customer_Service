from langchain_core.tools import tool

@tool
def apply_for_refund(order_id: str, reason: str, amount: float = 0.0):
    """
    当客户明确要求退款（如退钱、申请退款）时，必须调用此工具。
    你需要尝试从上下文中提取订单号(order_id)和退款原因(reason)。如果用户没说，可传入"未知"。
    """
    # LangGraph 架构下，工具函数体通常为空 (pass)，
    # 因为我们会在后续的 process_refund_ticket 节点统一拦截并执行数据库写入。
    pass

@tool
def check_logistics(order_id: str):
    """
    【预留示例】当客户要求查询快递物流进度时调用。
    """
    pass