from app.knowledge.repository import KnowledgeRepository


class KnowledgeService:
    """向售后工具提供稳定的知识检索结果"""

    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    async def search_support_knowledge(
        self,
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> dict:
        normalized_query = query.strip()
        if not normalized_query:
            return {
                "ok": False,
                "error_code": "EMPTY_KNOWLEDGE_QUERY",
                "message": "请提供需要查询的问题",
            }

        safe_limit = max(limit, 1)
        try:
            articles = await self.repository.search(
                normalized_query,
                category=category,
                limit=safe_limit,
            )
        except Exception:
            return {
                "ok": False,
                "error_code": "KNOWLEDGE_BACKEND_ERROR",
                "message": "知识库暂时不可用",
            }

        return {
            "ok": True,
            "count": len(articles),
            "articles": [article.to_public_dict() for article in articles],
        }
