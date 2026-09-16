from typing import Optional
from repo_intelligence.retrieval.base import VectorStore
from repo_intelligence.retrieval.in_memory import InMemoryVectorStore
from repo_intelligence.retrieval.qdrant_store import QdrantStore


class VectorStoreFactory:
    _stores = {
        "memory": InMemoryVectorStore,
        "qdrant": QdrantStore,
    }

    @classmethod
    def get_store(cls, name: str, **kwargs) -> Optional[VectorStore]:
        store_class = cls._stores.get(name)
        if store_class:
            return store_class(**kwargs)
        return None

    @classmethod
    def available_stores(cls):
        return list(cls._stores.keys())
