from __future__ import annotations
import re
from collections import Counter
from typing import List, Dict, Any

from repo_intelligence.retrieval.base import VectorStore


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())


class InMemoryVectorStore(VectorStore):
    """Simple in-memory retrieval store.

    This is a keyword/frequency fallback. A production deployment can swap it
    for a real vector database such as Qdrant.
    """

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.index: Dict[str, Counter] = {}

    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        tokens = _tokenize(text)
        self.documents.append({
            "id": doc_id,
            "text": text,
            "metadata": metadata,
            "tokens": tokens,
        })
        self.index[doc_id] = Counter(tokens)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        query_tokens = _tokenize(query)
        query_counter = Counter(query_tokens)

        scores = []
        for doc in self.documents:
            if filters:
                if not all(doc["metadata"].get(k) == v for k, v in filters.items()):
                    continue
            doc_counter = self.index[doc["id"]]
            common = query_counter & doc_counter
            score = sum(common.values())
            if score > 0:
                scores.append({**doc, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]

    def close(self) -> None:
        self.documents.clear()
        self.index.clear()
