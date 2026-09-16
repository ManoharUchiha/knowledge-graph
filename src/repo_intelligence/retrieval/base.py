from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class VectorStore(ABC):
    """Abstract vector/keyword retrieval store for repository artifacts."""

    @abstractmethod
    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Index a document chunk."""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Return the most relevant documents for a query."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release any resources."""
        pass
