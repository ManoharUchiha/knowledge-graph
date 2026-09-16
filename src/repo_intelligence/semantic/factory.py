from typing import Dict, List, Optional
from repo_intelligence.semantic.base import SemanticResolver
from repo_intelligence.semantic.jedi_resolver import JediResolver
from repo_intelligence.semantic.scip_resolver import ScipResolver
from repo_intelligence.semantic.lsp_resolver import LspResolver
from repo_intelligence.semantic.joern_resolver import JoernResolver


class SemanticResolverFactory:
    _resolvers: Dict[str, type] = {
        "jedi": JediResolver,
        "scip": ScipResolver,
        "lsp": LspResolver,
        "joern": JoernResolver,
    }

    @classmethod
    def get_resolver(cls, name: str) -> Optional[SemanticResolver]:
        resolver_class = cls._resolvers.get(name)
        if resolver_class:
            return resolver_class()
        return None

    @classmethod
    def available_resolvers(cls) -> List[str]:
        return list(cls._resolvers.keys())
