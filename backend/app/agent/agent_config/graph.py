from typing import Literal

from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.State.state import SCRMState
from app.agent.nodes.refund_ticket_node import refund_ticket_node
from app.agent.nodes.sale_node import create_sale_node
from app.agent.nodes.summarize_node import MIN_TOKENS_TO_COMPRESS, summarize_node
from app.agent.nodes.supervisor_and_chat_node import chat_node, supervisor_node
from app.agent.nodes.support_classifier_node import support_classifier_node
from app.agent.nodes.support_node import create_support_node
from app.agent.tool.product_tools import create_product_tools
from app.agent.tool.support_tools import create_knowledge_tools, create_order_tools
from app.agent.tool.ticket_tools import create_ticket_tools
from app.knowledge.factory import create_knowledge_repository
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.order.factory import create_order_repository
from app.order.repository import OrderRepository
from app.order.service import OrderService
from app.product.factory import create_product_repository
from app.product.repository import ProductRepository
from app.product.service import ProductService
from app.ticket.factory import create_ticket_repository
from app.ticket.repository import TicketRepository
from app.ticket.service import TicketService


def route_main_intent(state: SCRMState) -> Literal["sale", "support", "chat"]:
    """根据主管节点的分类结果路由"""
    intent = state.get("current_intent")
    if intent in {"sale", "support", "chat"}:
        return intent
    return "chat"


def route_support_intent(state: SCRMState) -> Literal["general", "refund"]:
    """根据售后细分结果路由"""
    intent = state.get("support_intent")
    if intent in {"general", "refund"}:
        return intent
    return "general"


def route_after_response(state: SCRMState) -> Literal["summarize", "end"]:
    """在消息达到压缩阈值时进入总结摘要节点"""
    messages = state.get("messages", [])
    if count_tokens_approximately(messages) >= MIN_TOKENS_TO_COMPRESS:
        return "summarize"
    return "end"


def route_tool_response(state: SCRMState) -> Literal["tools", "summarize", "end"]:
    """业务模型发起工具调用时进入对应 ToolNode，否则结束或压缩"""
    messages = state.get("messages", [])
    if messages and getattr(messages[-1], "tool_calls", None):
        return "tools"
    return route_after_response(state)


def build_graph(
    ticket_repository: TicketRepository | None = None,
    product_repository: ProductRepository | None = None,
    order_repository: OrderRepository | None = None,
    knowledge_repository: KnowledgeRepository | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """组装图；Repository 与 Checkpointer 均由 CLI/FastAPI 生命周期注入。"""
    ticket_repository = ticket_repository or create_ticket_repository()
    product_repository = product_repository or create_product_repository()
    order_repository = order_repository or create_order_repository()
    knowledge_repository = knowledge_repository or create_knowledge_repository()

    #下面出现的警告不影响图的运行，主要原因是PyCharm静态类型误报，忽略即可
    product_tools = create_product_tools(ProductService(product_repository))
    support_tools = [
        *create_ticket_tools(TicketService(ticket_repository)),
        *create_order_tools(OrderService(order_repository)),
        *create_knowledge_tools(KnowledgeService(knowledge_repository)),
    ]

    builder = StateGraph(SCRMState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("sale", create_sale_node(product_tools))
    builder.add_node(
        "sale_tools",
        ToolNode(
            product_tools,
            #如果这里报警告，可以不用管这个警告，这是静态分析还没跟上真实解释器环境，如有疑惑可以查看ToolNode源码
            handle_tool_errors="商品查询工具暂时不可用，请稍后重试。",
        ),
    )
    builder.add_node("chat", chat_node)
    builder.add_node("support_classifier", support_classifier_node)
    builder.add_node("support", create_support_node(support_tools))
    builder.add_node(
        "support_tools",
        ToolNode(
            support_tools,
            handle_tool_errors="售后业务工具暂时不可用，请稍后重试。",
        ),
    )
    builder.add_node("refund_ticket", refund_ticket_node)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_main_intent,
        {
            "sale": "sale",
            "support": "support_classifier",
            "chat": "chat",
        },
    )
    builder.add_conditional_edges(
        "support_classifier",
        route_support_intent,
        {
            "general": "support",
            "refund": "refund_ticket",
        },
    )

    builder.add_conditional_edges(
        "sale",
        route_tool_response,
        {
            "tools": "sale_tools",
            "summarize": "summarize",
            "end": END,
        },
    )
    builder.add_edge("sale_tools", "sale")

    builder.add_conditional_edges(
        "support",
        route_tool_response,
        {
            "tools": "support_tools",
            "summarize": "summarize",
            "end": END,
        },
    )
    builder.add_edge("support_tools", "support")

    for response_node in ("chat", "refund_ticket"):
        builder.add_conditional_edges(
            response_node,
            route_after_response,
            {"summarize": "summarize", "end": END},
        )

    builder.add_edge("summarize", END)
    return builder.compile(checkpointer=checkpointer)
