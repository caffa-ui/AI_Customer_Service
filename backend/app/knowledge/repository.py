from typing import Protocol, runtime_checkable

from app.knowledge.models import KnowledgeArticle


@runtime_checkable
class KnowledgeRepository(Protocol):
    """知识数据源，后续可由RAG、数据库实现"""

    async def search(
        self,
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> list[KnowledgeArticle]:
        ...

    async def close(self) -> None:
        ...
