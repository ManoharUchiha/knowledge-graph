from typing import List, Dict, Any

from repo_intelligence.retrieval.base import VectorStore


class QdrantStore(VectorStore):
    """Qdrant-backed vector store (placeholder for Phase 3+).

    A full implementation would use qdrant-client + sentence-transformers
    (or another embedding model) to index and search code chunks.
    """

    def __init__(self, url: str = "http://localhost:6333", collection: str = "repo_intel"):
        self.url = url
        self.collection = collection

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        pass

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        return []

    def close(self) -> None:
        pass
