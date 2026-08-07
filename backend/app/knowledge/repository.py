from typing import Protocol, runtime_checkable

from app.knowledge.models import KnowledgeArticle


@runtime_checkable
class KnowledgeRepository(Protocol):
    """知识数据源协议，后续可由 RAG、数据库或外部 API 实现。"""

    async def search(
        self,
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> list[KnowledgeArticle]:
        ...

    async def close(self) -> None:
        ...
