import json
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.factory import get_embedding_model
from app.utils.config_handler import chroma_config
from app.utils.file_handler import get_file_md5_hex, pdf_loader, txt_loader
from app.utils.logger_handler import get_logger
from app.utils.path_tool import get_abs_path


class VectorStoreService:
    """负责RAG文档增量导入和Chroma向量检索"""

    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_config("collection_name"),
            embedding_function=get_embedding_model(),
            persist_directory=get_abs_path(chroma_config("persist_directory")),
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_config("chunk_size"),
            chunk_overlap=chroma_config("chunk_overlap"),
            separators=chroma_config("separators"),
            length_function=len,
        )
        self.logger = get_logger("vector_store")

    @staticmethod
    def _load_file_suffix(path: Path) -> list[Document]:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return txt_loader(str(path))
        if suffix == ".pdf":
            return pdf_loader(str(path))
        return []

    # 兼容旧测试与旧调用方；正式导入使用更明确的 _load_file_suffix。
    _load_file = _load_file_suffix

    def get_retriever(self):
        """保留旧式检索器入口，供 RagSummarizeService 等调用方使用。"""
        return self.vector_store.as_retriever(
            search_kwargs={"k": chroma_config("k")}
        )

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _collect_files(data_path: Path, allowed_types: set[str]) -> list[Path]:
        """扫描知识目录并筛选允许的文件类型"""
        if not data_path.is_dir():
            raise RuntimeError(f"RAG知识目录不存在: {data_path}")
        return sorted(
            path
            for path in data_path.rglob("*")
            if path.is_file() and path.suffix.lower() in allowed_types
        )

    def _remove_deleted_sources(
        self, manifest: dict[str, str], current_sources: set[str]
    ) -> None:
        """删除磁盘上已不存在的源文件对应的旧向量"""
        for source in list(manifest):
            if source in current_sources:
                continue
            existing = self.vector_store.get(
                where={"source": source},
                include=["metadatas"],
            )
            if existing.get("ids"):
                self.vector_store.delete(ids=existing["ids"])
            del manifest[source]

    def _ingest_file(self, path: Path, manifest: dict[str, str]) -> Optional[bool]:
        """导入更新文件；True=写入，False=跳过，None=摘要失败"""
        source = str(path.resolve())
        digest = get_file_md5_hex(source)
        if not digest:
            return None
        if manifest.get(source) == digest:
            return False

        # 通过兼容入口调用，方便旧调用方和测试替换文件加载器。
        documents = self._load_file(path)
        split_documents = self.splitter.split_documents(documents)
        if not split_documents:
            self.logger.warning(f"[加载知识库]{source}没有可导入的文本内容")
            return False

        for index, document in enumerate(split_documents):
            document.metadata.update(
                {
                    "source": source,
                    "source_name": path.name,
                    "chunk_index": index,
                }
            )

        old = self.vector_store.get(
            where={"source": source},
            include=["metadatas"],
        )
        new_ids = [f"{digest}:{index}" for index in range(len(split_documents))]
        self.vector_store.add_documents(split_documents, ids=new_ids)
        stale_ids = [
            document_id
            for document_id in old.get("ids", [])
            if document_id not in new_ids
        ]
        if stale_ids:
            self.vector_store.delete(ids=stale_ids)

        manifest[source] = digest
        self.logger.info(f"[加载知识库]{source}已写入 Chroma")
        return True

    def load_documents(self) -> dict[str, int]:
        """增量导入知识目录中的 TXT/PDF"""
        data_path = Path(get_abs_path(chroma_config("data_path")))
        manifest_path = Path(get_abs_path(chroma_config("md5_hex_store")))
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        allowed_types = {
            str(suffix).lower()
            for suffix in chroma_config("allowed_knowledge_file_type")
        }
        files = self._collect_files(data_path, allowed_types)
        manifest = self._read_manifest(manifest_path)
        current_sources = {str(path.resolve()) for path in files}
        self._remove_deleted_sources(manifest, current_sources)
        loaded_files = 0
        skipped_files = 0

        for path in files:
            result = self._ingest_file(path, manifest)
            if result is False:
                skipped_files += 1
            elif result is True:
                loaded_files += 1

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "loaded_files": loaded_files,
            "skipped_files": skipped_files,
            "total_files": len(files),
        }

    def load_document(self) -> dict[str, int]:
        """兼容旧方法名。"""
        return self.load_documents()

    def similarity_search(
        self,
        query: str,
        limit: int = 3,
    ) -> list[tuple[Document, float]]:
        results = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=limit,
            score_threshold=0.5
        )
        min_score = float(chroma_config("min_relevance_score"))
        return [
            (document, score)
            for document, score in results
            if score >= min_score
        ]

    def close(self) -> None:
        return None
