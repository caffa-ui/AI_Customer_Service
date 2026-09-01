from langchain_core.tools import BaseTool
from langchain.tools import tool

from app.knowledge.service import KnowledgeService


def create_knowledge_tools(service: KnowledgeService) -> list[BaseTool]:
    """为售后智能体创建离线知识检索工具。"""

    @tool(parse_docstring = True)
    async def search_support_knowledge(
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> dict:
        """
        查询故障排查、退换货规则、物流服务等售后知识。
        用户需要处理步骤或规则说明时调用；查询结果为空时不要自行编造规则。
        category 不明确时留空，limit 通常不超过 3。

        Args:
            query:

        """
        return await service.search_support_knowledge(query, category, limit)

    return [search_support_knowledge]


