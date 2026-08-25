from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from app.knowledge.service import KnowledgeService
from app.order.service import OrderService


def create_order_tools(service: OrderService) -> list[BaseTool]:
    """为售后智能体创建带用户隔离的订单与物流工具"""

    @tool(parse_docstring=True)
    async def query_order(order_id: str, runtime: ToolRuntime) -> dict:
        """
        根据订单号查询当前登录用户自己的订单详情
        仅在用户提供明确订单号时调用；不得查询或猜测其他用户的订单

        Args:
            order_id: 用户的订单单号

        """
        user_id = runtime.state.get("user_id", "")
        return await service.query_order(order_id, user_id)

    @tool(parse_docstring=True)
    async def check_logistics(order_id: str, runtime: ToolRuntime) -> dict:
        """
        根据订单号查询当前登录用户自己的承运商、运单号和最新物流进度
        物流状态必须以本工具本轮返回结果为准；用户未提供订单号时先询问

        Args:
            order_id: 用户的订单单号

        """
        user_id = runtime.state.get("user_id", "")
        return await service.check_logistics(order_id, user_id)

    return [query_order, check_logistics]


def create_knowledge_tools(service: KnowledgeService) -> list[BaseTool]:
    """为售后智能体创建离线知识检索工具。"""

    @tool
    async def search_support_knowledge(
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> dict:
        """
        查询故障排查、退换货规则、物流服务等售后知识。
        用户需要处理步骤或规则说明时调用；查询结果为空时不要自行编造规则。
        category 不明确时留空，limit 通常不超过 3。
        """
        return await service.search_support_knowledge(query, category, limit)

    return [search_support_knowledge]
