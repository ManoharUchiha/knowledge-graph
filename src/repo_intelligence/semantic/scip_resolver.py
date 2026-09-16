from repo_intelligence.semantic.base import SemanticResolver
from repo_intelligence.models.core import RepositoryModel


class ScipResolver(SemanticResolver):
    """SCIP-based semantic resolver (placeholder for Phase 2+).

    In a full implementation this would read a generated SCIP index (protobuf)
    and merge its precise symbol/call relationships into the repository model.
    """

    name = "scip"

    def supports(self, language: str) -> bool:
        return True

    def resolve(self, model: RepositoryModel, root_path: str) -> RepositoryModel:
        return model
