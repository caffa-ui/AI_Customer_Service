from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from app.ticket.service import TicketService


def create_ticket_tools(service: TicketService) -> list[BaseTool]:
    """为工单服务创建工具并注入Repository。"""

    @tool(parse_docstring=True)
    async def list_my_tickets(runtime: ToolRuntime) -> dict:
        """
        查询当前登录用户的工单列表
        当用户说“查询我的工单”、“我有哪些售后申请”或未提供具体工单号时调用
        用户身份可从会话状态中自动获取，不要向用户索要 user_i

        """
        user_id = runtime.state.get("user_id", "")
        return await service.list_my_tickets(user_id)

    @tool(parse_docstring=True)
    async def query_ticket(ticket_id: str, runtime: ToolRuntime) -> dict:
        """
        根据工单号查询当前登录用户的工单详情和处理进度
        只在用户提供了明确工单号时调用；如果没有工单号，请改用 list_my_tickets

        Args:
            ticket_id: 工单号

        """
        user_id = runtime.state.get("user_id", "")
        return await service.query_ticket(ticket_id, user_id)

    @tool(parse_docstring=True)
    async def create_support_ticket(
        subject: str,
        description: str,
        runtime: ToolRuntime,
    ) -> dict:
        """
        为当前登录用户创建普通人工售后工单
        仅当自动排查无法解决问题，并且用户明确同意创建工单后调用
        不要用于退款申请
        用户身份从可信会话状态中自动获取，不要向用户索要 user_id

        Args:
            subject:简短主题
            description:已确认的问题描述

        """
        user_id = runtime.state.get("user_id", "")
        return await service.create_support_ticket(subject, description, user_id)

    return [list_my_tickets, query_ticket, create_support_ticket]
