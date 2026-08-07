import os

from app.knowledge.rag_repository import RagKnowledgeRepository
from app.knowledge.repository import KnowledgeRepository
from app.utils.config_handler import agent_config


def create_knowledge_repository() -> KnowledgeRepository:
    knowledge_config = agent_config.get("knowledge", {})
    backend = os.getenv(
        "KNOWLEDGE_REPOSITORY",
        knowledge_config.get("repository", "rag"),
    ).strip().lower()

    if backend == "rag":
        return RagKnowledgeRepository()

    raise ValueError(
        f"不支持的知识数据源: {backend}；当前知识库仅支持 rag"
    )
