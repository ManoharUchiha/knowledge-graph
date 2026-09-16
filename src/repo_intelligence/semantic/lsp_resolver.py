from repo_intelligence.semantic.base import SemanticResolver
from repo_intelligence.models.core import RepositoryModel


class LspResolver(SemanticResolver):
    """LSP-based semantic resolver (placeholder for Phase 2+).

    A full implementation would spawn or connect to a language server
    (e.g. python-lsp-server, pyright, clangd, gopls) and use LSP
    textDocument/definition requests to resolve symbols cross-file.
    """

    name = "lsp"

    def supports(self, language: str) -> bool:
        return True

    def resolve(self, model: RepositoryModel, root_path: str) -> RepositoryModel:
        return model
