import asyncio
from collections.abc import Callable
from pathlib import Path

from app.knowledge.models import KnowledgeArticle
from app.rag.vector_store import VectorStoreService


class RagKnowledgeRepository:
    """使用 Google Embedding 与 Chroma 的售后知识 Repository。"""

    def __init__(
        self,
        vector_store_factory: Callable[[], VectorStoreService] = VectorStoreService,
    ):
        self._vector_store_factory = vector_store_factory
        self._vector_store: VectorStoreService | None = None
        self._initialization_lock = asyncio.Lock()

    async def _get_vector_store(self) -> VectorStoreService:
        if self._vector_store is not None:
            return self._vector_store

        async with self._initialization_lock:
            if self._vector_store is None:
                vector_store = await asyncio.to_thread(self._vector_store_factory)
                try:
                    await asyncio.to_thread(vector_store.load_documents)
                except Exception:
                    await asyncio.to_thread(vector_store.close)
                    raise
                self._vector_store = vector_store
        return self._vector_store

    async def search(
        self,
        query: str,
        category: str = "",
        limit: int = 3,
    ) -> list[KnowledgeArticle]:
        vector_store = await self._get_vector_store()
        search_query = " ".join(
            part for part in (category.strip(), query.strip()) if part
        )
        results = await asyncio.to_thread(
            vector_store.similarity_search,
            search_query,
            limit,
        )

        articles: list[KnowledgeArticle] = []
        for index, (document, score) in enumerate(results, start=1):
            metadata = document.metadata or {}
            source_path = str(metadata.get("source", ""))
            source_name = str(
                metadata.get("source_name")
                or (Path(source_path).name if source_path else "RAG 知识文档")
            )
            raw_page = metadata.get("page")
            page = int(raw_page) + 1 if isinstance(raw_page, int) else None
            chunk_index = metadata.get("chunk_index", index)
            article_id = f"{source_name}#chunk-{chunk_index}"

            articles.append(
                KnowledgeArticle(
                    article_id=article_id,
                    title=source_name,
                    category=category.strip() or "RAG 知识库",
                    content=document.page_content,
                    source_type="rag",
                    source_path=source_name,
                    page=page,
                    score=max(0.0, min(float(score), 1.0)),
                )
            )
        return articles

    async def close(self) -> None:
        if self._vector_store is not None:
            await asyncio.to_thread(self._vector_store.close)
            self._vector_store = None
