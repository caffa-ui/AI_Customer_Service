from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

from langchain_core.documents import Document

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app.rag.vector_store as vector_store_module
from app.rag.vector_store import VectorStoreService


class CallableConfig(dict):
    def __call__(self, key: str):
        return self[key]


class FakeSplitter:
    def split_documents(self, documents):
        return documents


class FakeLogger:
    def info(self, message):
        return None

    def warning(self, message):
        return None


class FakeChroma:
    def __init__(self):
        self.ids_by_source: dict[str, list[str]] = {}

    def get(self, where, include):
        source = where["source"]
        return {"ids": list(self.ids_by_source.get(source, []))}

    def add_documents(self, documents, ids):
        source = documents[0].metadata["source"]
        existing = self.ids_by_source.setdefault(source, [])
        for document_id in ids:
            if document_id not in existing:
                existing.append(document_id)

    def delete(self, ids):
        for source, existing in self.ids_by_source.items():
            self.ids_by_source[source] = [
                document_id for document_id in existing if document_id not in ids
            ]


class VectorStoreIngestionTests(unittest.TestCase):
    def test_incremental_import_update_and_delete(self):
        knowledge_dir = Path("virtual/knowledge")
        document_path = knowledge_dir / "guide.txt"
        manifest_path = knowledge_dir / ".ingested.json"
        state = {
            "files": [document_path],
            "digest": "digest-v1",
            "content": "第一版售后说明",
        }
        manifest: dict[str, str] = {}

        config = CallableConfig(
            data_path=str(knowledge_dir),
            md5_hex_store=str(manifest_path),
            allowed_knowledge_file_type=[".txt"],
        )
        service = object.__new__(VectorStoreService)
        service.vector_store = FakeChroma()
        service.splitter = FakeSplitter()
        service.logger = FakeLogger()

        def remember_manifest(path, content, encoding):
            manifest.clear()
            manifest.update(json.loads(content))
            return len(content)

        with (
            patch.object(vector_store_module, "chroma_config", config),
            patch.object(vector_store_module, "get_abs_path", lambda path: path),
            patch.object(Path, "mkdir", lambda *args, **kwargs: None),
            patch.object(Path, "is_dir", lambda path: True),
            patch.object(Path, "is_file", lambda path: True),
            patch.object(
                Path,
                "rglob",
                lambda path, pattern: list(state["files"]),
            ),
            patch.object(
                Path,
                "write_text",
                remember_manifest,
            ),
            patch.object(
                service,
                "_read_manifest",
                lambda path: dict(manifest),
            ),
            patch.object(
                service,
                "_load_file",
                lambda path: [
                    Document(
                        page_content=state["content"],
                        metadata={},
                    )
                ],
            ),
            patch.object(
                vector_store_module,
                "get_file_md5_hex",
                lambda path: state["digest"],
            ),
        ):
            first = service.load_documents()
            second = service.load_documents()
            first_ids = list(
                service.vector_store.ids_by_source[str(document_path.resolve())]
            )

            state["digest"] = "digest-v2"
            state["content"] = "第二版售后说明"
            updated = service.load_documents()
            updated_ids = list(
                service.vector_store.ids_by_source[str(document_path.resolve())]
            )

            state["files"] = []
            removed = service.load_documents()

        self.assertEqual(first["loaded_files"], 1)
        self.assertEqual(second["skipped_files"], 1)
        self.assertEqual(updated["loaded_files"], 1)
        self.assertNotEqual(first_ids, updated_ids)
        self.assertEqual(removed["total_files"], 0)
        self.assertEqual(
            service.vector_store.ids_by_source[str(document_path.resolve())],
            [],
        )


if __name__ == "__main__":
    unittest.main()
