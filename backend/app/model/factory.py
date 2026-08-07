import os
from pathlib import Path
from app.utils.logger_handler import get_logger
from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_core.callbacks import BaseCallbackHandler
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
from app.utils.config_handler import rag_config
from app.utils.path_tool import get_abs_path

load_dotenv(Path(get_abs_path("")).parent / ".env", override=False)

logger = get_logger("gemini_factory")

# 可观测性探针：用于返回token使用情况
class GeminiTokenUsageCallback(BaseCallbackHandler):
    """
    拦截 Google API 的底层响应。
    Gemini 的 Token 统计数据结构与 OpenAI 协议不同，必须精准提取。
    """
    def on_llm_end(self, response, **kwargs):
        try:
            # 尝试从 llm_output 或生成信息中提取 usage_metadata
            usage = response.llm_output.get("usage_metadata", {})
            if not usage and response.generations:
                info = response.generations[0][0].generation_info or {}
                usage = info.get("usage_metadata", {})

            total_tokens = usage.get("total_token_count", 0)
            prompt_tokens = usage.get("prompt_token_count", 0)
            candidates_tokens = usage.get("candidates_token_count", 0)

            logger.info(
                f"[计费与性能监控] 交互结束. 总 Token: {total_tokens} (Prompt: {prompt_tokens}, 生成: {candidates_tokens})")
        except Exception as e:
            logger.error(f"[计费与性能监控] 提取 Gemini Token 数据失败: {str(e)}")


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass

class ChatModelFactory(BaseModelFactory):
    _instance: Optional[BaseChatModel] = None  # 引入类变量缓存单例

    def generator(self) -> BaseChatModel:
        # 核心防线：单例拦截。如果已经实例化过，直接返回内存中的对象，拒绝重复创建。
        if self._instance is not None:
            return self._instance

        # Google 生成式 SDK 底层使用的是基于 gRPC/REST 的通道。
        # 我们不能像对付 OpenAI 那样直接塞入 httpx.Client，必须通过 timeout 和 max_retries 来施加控制。
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or rag_config.get("gemini_api_key")
        if not api_key:
            raise RuntimeError("启用 RAG 前请在 backend/.env 中配置 GOOGLE_API_KEY 或 GEMINI_API_KEY")

        type(self)._instance = ChatGoogleGenerativeAI(
            model=rag_config("chat_model_name"),
            google_api_key=api_key,

            # 强制设定温度，消除幻觉变量（根据你的实际需要调整）
            temperature=0,

            # 防御机制 1：限定底层 SDK 遇到网络或服务端 5xx 错误时的最大重试次数
            max_retries=3,

            # 防御机制 2：绝对超时界限。任何超过 30 秒无响应的请求将被强行掐断，释放线程资源
            timeout=30.0,

            # 挂载监控探针
            callbacks=[GeminiTokenUsageCallback()]
        )
        logger.info("Gemini Chat 模型实体已装载入内存 (单例)。")
        return type(self)._instance

class EmbeddingModelFactory(BaseModelFactory):
    _instance: Optional[Embeddings] = None

    def generator(self) -> Embeddings:
        if self._instance is not None:
            return self._instance

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or rag_config.get("gemini_api_key")
        if not api_key:
            raise RuntimeError("导入 RAG 知识库前请在 backend/.env 中配置 GOOGLE_API_KEY 或 GEMINI_API_KEY")

        type(self)._instance = GoogleGenerativeAIEmbeddings(
            model=rag_config("embedding_model_name"),
            google_api_key=api_key,
        )
        logger.info("Gemini Embedding 模型实体已装载入内存 (单例)。")
        return type(self)._instance


def get_chat_model() -> BaseChatModel:
    """按需创建 RAG 对话模型，不影响主客服流程启动。"""
    return ChatModelFactory().generator()


def get_embedding_model() -> Embeddings:
    """按需创建 Embedding 模型。"""
    return EmbeddingModelFactory().generator()
