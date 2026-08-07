from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.vector_store import VectorStoreService


def main() -> None:
    """将知识目录中的 TXT/PDF 增量写入本地 Chroma。"""
    vector_store = VectorStoreService()
    try:
        result = vector_store.load_documents()
    finally:
        vector_store.close()

    print(
        "RAG 知识导入完成："
        f"新增/更新 {result['loaded_files']} 个，"
        f"跳过 {result['skipped_files']} 个，"
        f"共扫描 {result['total_files']} 个。"
    )


if __name__ == "__main__":
    main()
