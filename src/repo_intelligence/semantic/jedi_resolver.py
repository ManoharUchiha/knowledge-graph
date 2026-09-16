from __future__ import annotations
import os
from typing import Dict, Optional, Tuple
import jedi

from repo_intelligence.semantic.base import SemanticResolver
from repo_intelligence.models.core import (
    RepositoryModel,
    SymbolType,
    RelationType,
    Evidence,
)


class JediResolver(SemanticResolver):
    """Semantic resolver powered by Jedi.

    Resolves unresolved call and inheritance targets to concrete symbols within
    the repository. This gives the graph LSP-like accuracy for Python without
    requiring a running language server.
    """

    name = "jedi"

    def supports(self, language: str) -> bool:
        return language == "python"

    def resolve(self, model: RepositoryModel, root_path: str) -> RepositoryModel:
        try:
            project = jedi.Project(root_path)
        except Exception:  # pylint: disable=broad-except
            project = None

        # Cache jedi.Script instances and file sources.
        scripts: Dict[str, jedi.Script] = {}
        sources: Dict[str, str] = {}

        def _get_script(file_path: str) -> Optional[jedi.Script]:
            abs_path = os.path.join(root_path, file_path)
            if abs_path not in scripts:
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        sources[abs_path] = f.read()
                except Exception:  # pylint: disable=broad-except
                    return None
                scripts[abs_path] = jedi.Script(
                    sources[abs_path], path=abs_path, project=project
                )
            return scripts[abs_path]

        # Build lookup tables from absolute file path + name to symbol id.
        # We keep both short names and qualified names because Jedi may return
        # either depending on context.
        symbol_by_qname: Dict[Tuple[str, str], str] = {}
        symbol_by_short_name: Dict[Tuple[str, str], str] = {}
        for sym in model.symbols:
            if sym.symbol_type not in (
                SymbolType.FUNCTION,
                SymbolType.METHOD,
                SymbolType.CLASS,
            ):
                continue
            abs_path = os.path.join(root_path, sym.location.file_path)
            qname = sym.id.split(":")[-1]
            symbol_by_qname[(abs_path, qname)] = sym.id
            symbol_by_short_name[(abs_path, sym.name)] = sym.id

        symbol_by_id = {sym.id: sym for sym in model.symbols}

        for rel in model.relationships:
            if not rel.target_id.startswith("unresolved:"):
                continue
            if rel.rel_type not in (RelationType.CALLS, RelationType.INHERITS):
                continue

            source_sym = symbol_by_id.get(rel.source_id)
            if not source_sym:
                continue
            if not source_sym.location.file_path.endswith(".py"):
                continue

            script = _get_script(source_sym.location.file_path)
            if not script:
                continue

            if not rel.evidence:
                continue
            evidence = rel.evidence[0]
            line = evidence.start_line
            col = evidence.start_col
            if line is None or col is None:
                continue

            # For attribute calls like service.create_order(), point Jedi at the
            # final identifier (create_order) rather than the object (service).
            callee_name = rel.metadata.get("callee_name") or rel.metadata.get("base_name") or ""
            if "." in callee_name:
                col = col + callee_name.rfind(".") + 1

            try:
                definitions = script.infer(line, col)
            except Exception:  # pylint: disable=broad-except
                continue

            target_id = self._pick_definition(
                definitions,
                root_path,
                symbol_by_qname,
                symbol_by_short_name,
            )
            if target_id:
                rel.target_id = target_id
                rel.confidence = 0.95
                rel.metadata["resolution_status"] = "jedi-resolved"
                rel.metadata["resolver"] = "jedi"
                rel.evidence.append(
                    Evidence(
                        type="jedi",
                        file_path=evidence.file_path,
                        start_line=line,
                        start_col=col,
                        confidence=0.95,
                    )
                )

        return model

    @staticmethod
    def _pick_definition(
        definitions,
        root_path: str,
        symbol_by_qname: Dict[Tuple[str, str], str],
        symbol_by_short_name: Dict[str, str],
    ) -> Optional[str]:
        for d in definitions:
            module_path = str(d.module_path) if d.module_path else None
            if not module_path or not module_path.startswith(str(root_path)):
                continue

            full_name = d.full_name
            if full_name:
                key = (module_path, full_name)
                if key in symbol_by_qname:
                    return symbol_by_qname[key]
                # Full name may include class path; try the last segment too.
                short = full_name.split(".")[-1]
                key2 = (module_path, short)
                if key2 in symbol_by_short_name:
                    return symbol_by_short_name[key2]

            # Fallback to the definition's own name.
            key = (module_path, d.name)
            if key in symbol_by_short_name:
                return symbol_by_short_name[key]

        return None
