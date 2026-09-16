from repo_intelligence.semantic.base import SemanticResolver
from repo_intelligence.models.core import RepositoryModel


class JoernResolver(SemanticResolver):
    """Joern-based semantic resolver (placeholder for Phase 2+).

    Joern is most useful for C/C++/Java/JVM code. A full implementation would
    ingest the Joern CPG and translate its call/data/control-flow edges into
    the repository model.
    """

    name = "joern"

    def supports(self, language: str) -> bool:
        return True

    def resolve(self, model: RepositoryModel, root_path: str) -> RepositoryModel:
        return model
