import os

from pathlib import Path

from app.utils.logger_handler import get_logger
from typing import Optional
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
from app.utils.config_handler import rag_config

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

logger = get_logger("gemini_embedding_factory")

class EmbeddingModelFactory:
    _instance: Optional[Embeddings] = None

    def generator(self) -> Embeddings:
        if self._instance is not None:
            return self._instance

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.info("向量模型载入失败")
            raise RuntimeError("请在导入 RAG 知识库前请在 backend/.env 中配置 GOOGLE_API_KEY 或 GEMINI_API_KEY")

        type(self)._instance = GoogleGenerativeAIEmbeddings(
            model=rag_config("embedding_model_name"),
            google_api_key=api_key,
        )
        logger.info("谷歌Embedding模型实体已装载入")

        return type(self)._instance

def get_embedding_model() -> Embeddings:
    """按需创建谷歌向量模型"""
    return EmbeddingModelFactory().generator()
