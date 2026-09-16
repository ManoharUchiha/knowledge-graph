from __future__ import annotations
from abc import ABC, abstractmethod
from repo_intelligence.models.core import RepositoryModel


class SemanticResolver(ABC):
    """Base class for semantic analysis backends.

    A semantic resolver takes an intermediate repository model (built by the
    language parsers) and enriches it with cross-file, type-aware relationships
    such as resolved calls, inheritance, and type references.

    Backends may wrap tools such as Jedi, SCIP, LSP, or Joern.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable resolver name."""
        pass

    @abstractmethod
    def supports(self, language: str) -> bool:
        """Return True if this resolver can handle the given language."""
        pass

    @abstractmethod
    def resolve(self, model: RepositoryModel, root_path: str) -> RepositoryModel:
        """Enrich the model with resolved relationships and return it."""
        pass
