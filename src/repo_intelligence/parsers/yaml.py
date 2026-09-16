from __future__ import annotations
from typing import List, Tuple, Dict, Any
import tree_sitter_yaml as tsyaml
from tree_sitter import Language
from repo_intelligence.parsers.base import BaseParser
from repo_intelligence.models.core import (
    Symbol,
    Relationship,
    SymbolType,
    RelationType,
    SourceLocation,
    Evidence,
)


class YamlParser(BaseParser):
    def __init__(self, context):
        super().__init__(Language(tsyaml.language()), context)

    def parse(self, file_path: str, source_code: bytes) -> Tuple[List[Symbol], List[Relationship]]:
        tree = self.parser.parse(source_code)
        root_node = tree.root_node

        symbols: List[Symbol] = []
        relationships: List[Relationship] = []
        file_id = self._make_file_id(file_path)

        # A YAML stream can contain multiple documents.
        documents = [c for c in root_node.children if c.type == "document"]
        if not documents:
            documents = [root_node]

        for doc in documents:
            yaml_data = self._parse_node(doc, source_code)
            if not isinstance(yaml_data, dict):
                continue

            self._extract_document(file_path, doc, yaml_data, file_id, symbols, relationships)

        return symbols, relationships

    def _extract_document(
        self,
        file_path: str,
        doc_node,
        yaml_data: Dict[str, Any],
        file_id: str,
        symbols: List[Symbol],
        relationships: List[Relationship],
    ):
        api_version = yaml_data.get("apiVersion")
        kind = yaml_data.get("kind")
        if not api_version or not kind:
            return

        metadata = yaml_data.get("metadata", {}) if isinstance(yaml_data.get("metadata"), dict) else {}
        name = metadata.get("name", "unknown") if isinstance(metadata, dict) else "unknown"

        start_line = doc_node.start_point[0] + 1
        end_line = doc_node.end_point[0] + 1

        resource_symbol_id = self._make_symbol_id(file_path, f"k8s:{kind}:{name}")
        resource_symbol = Symbol(
            id=resource_symbol_id,
            repo=self.context.repo_name,
            branch=self.context.branch,
            commit=self.context.commit,
            name=name,
            symbol_type=SymbolType.RESOURCE,
            location=SourceLocation(
                file_path=file_path,
                start_line=start_line,
                start_col=doc_node.start_point[1],
                end_line=end_line,
                end_col=doc_node.end_point[1],
            ),
            metadata={
                "kind": kind,
                "apiVersion": api_version,
            },
        )
        symbols.append(resource_symbol)

        relationships.append(
            Relationship(
                source_id=file_id,
                target_id=resource_symbol_id,
                rel_type=RelationType.KUBERNETES_OBJECT,
                repo=self.context.repo_name,
                branch=self.context.branch,
                commit=self.context.commit,
                evidence=[
                    Evidence(
                        type="static",
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        confidence=0.95,
                    )
                ],
            )
        )

        # Crossplane-specific relationship extraction
        spec = yaml_data.get("spec", {}) if isinstance(yaml_data.get("spec"), dict) else {}

        if kind == "CompositeResourceDefinition":
            group = spec.get("group") or api_version.split("/")[0]
            names = spec.get("names", {})
            composite_kind = names.get("kind")
            if composite_kind and group:
                type_symbol_id = self._type_symbol_id(group, composite_kind)
                symbols.append(
                    Symbol(
                        id=type_symbol_id,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        name=composite_kind,
                        symbol_type=SymbolType.RESOURCE_TYPE,
                        location=resource_symbol.location,
                        metadata={
                            "group": group,
                            "kind": composite_kind,
                            "scope": spec.get("scope"),
                            "claimNames": spec.get("claimNames", {}).get("kind"),
                        },
                    )
                )
                relationships.append(
                    Relationship(
                        source_id=resource_symbol_id,
                        target_id=type_symbol_id,
                        rel_type=RelationType.DEFINES,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        evidence=[Evidence(type="static", file_path=file_path, start_line=start_line, end_line=end_line)],
                    )
                )

        elif kind == "Composition":
            composite_type_ref = spec.get("compositeTypeRef", {})
            ref_api_version = composite_type_ref.get("apiVersion")
            ref_kind = composite_type_ref.get("kind")
            if ref_api_version and ref_kind:
                ref_group = ref_api_version.split("/")[0] if "/" in ref_api_version else ref_api_version
                type_symbol_id = self._type_symbol_id(ref_group, ref_kind)
                symbols.append(
                    Symbol(
                        id=type_symbol_id,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        name=ref_kind,
                        symbol_type=SymbolType.RESOURCE_TYPE,
                        location=resource_symbol.location,
                        metadata={"group": ref_group, "kind": ref_kind},
                    )
                )
                relationships.append(
                    Relationship(
                        source_id=resource_symbol_id,
                        target_id=type_symbol_id,
                        rel_type=RelationType.COMPOSITES,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        evidence=[Evidence(type="static", file_path=file_path, start_line=start_line, end_line=end_line)],
                    )
                )

            # Function references in pipeline mode
            pipeline = spec.get("pipeline", [])
            if isinstance(pipeline, list):
                for step in pipeline:
                    if not isinstance(step, dict):
                        continue
                    function_ref = step.get("functionRef", {})
                    function_name = function_ref.get("name") if isinstance(function_ref, dict) else None
                    if function_name:
                        function_symbol_id = f"fn:{function_name}"
                        symbols.append(
                            Symbol(
                                id=function_symbol_id,
                                repo=self.context.repo_name,
                                branch=self.context.branch,
                                commit=self.context.commit,
                                name=function_name,
                                symbol_type=SymbolType.MODULE,
                                location=resource_symbol.location,
                                metadata={"kind": "Function"},
                            )
                        )
                        relationships.append(
                            Relationship(
                                source_id=resource_symbol_id,
                                target_id=function_symbol_id,
                                rel_type=RelationType.USES,
                                repo=self.context.repo_name,
                                branch=self.context.branch,
                                commit=self.context.commit,
                                evidence=[Evidence(type="static", file_path=file_path, start_line=start_line, end_line=end_line)],
                            )
                        )

            # Classic (resources-mode) Compositions: each base is a managed resource.
            resources = spec.get("resources", [])
            if isinstance(resources, list):
                for entry in resources:
                    base = entry.get("base") if isinstance(entry, dict) else None
                    if not isinstance(base, dict):
                        continue
                    base_kind = base.get("kind")
                    base_api = base.get("apiVersion")
                    if not base_kind:
                        continue
                    mr_type_id = f"mrtype:{base_api}:{base_kind}" if base_api else f"mrtype:{base_kind}"
                    symbols.append(
                        Symbol(
                            id=mr_type_id,
                            repo=self.context.repo_name,
                            branch=self.context.branch,
                            commit=self.context.commit,
                            name=base_kind,
                            symbol_type=SymbolType.RESOURCE_TYPE,
                            location=resource_symbol.location,
                            metadata={"kind": base_kind, "apiVersion": base_api},
                        )
                    )
                    relationships.append(
                        Relationship(
                            source_id=resource_symbol_id,
                            target_id=mr_type_id,
                            rel_type=RelationType.CREATES,
                            repo=self.context.repo_name,
                            branch=self.context.branch,
                            commit=self.context.commit,
                            evidence=[Evidence(type="static", file_path=file_path, start_line=start_line, end_line=end_line)],
                        )
                    )

    def _type_symbol_id(self, group: str, kind: str) -> str:
        return f"xrdtype:{group}:{kind}"

    def _parse_node(self, node, source_code: bytes) -> Any:
        """Recursive helper to convert tree-sitter YAML AST to a Python object."""
        if node.type == "stream":
            return self._parse_node(node.children[0], source_code) if node.children else {}
        if node.type == "document":
            return self._parse_node(node.children[0], source_code) if node.children else {}
        if node.type == "block_node":
            return self._parse_node(node.children[0], source_code) if node.children else {}
        if node.type == "flow_node":
            return self._parse_node(node.children[0], source_code) if node.children else ""
        if node.type == "block_mapping":
            return self._parse_mapping(node, source_code)
        if node.type == "flow_mapping":
            return self._parse_flow_mapping(node, source_code)
        if node.type == "block_sequence":
            return [self._parse_node(child, source_code) for child in node.children if child.type != "-"]
        if node.type == "flow_sequence":
            return [
                self._parse_node(child, source_code)
                for child in node.children
                if child.type == "flow_node"
            ]
        if node.type == "block_sequence_item":
            for child in node.children:
                if child.type not in ("-", ":"):
                    return self._parse_node(child, source_code)
            return None
        if node.type == "block_mapping_pair":
            return self._parse_mapping_pair(node, source_code)
        if node.type in ("plain_scalar", "string_scalar"):
            return self._get_node_text(node, source_code).strip(" '")

        if not node.children:
            return self._get_node_text(node, source_code).strip(" '")

        return self._parse_node(node.children[0], source_code) if node.children else ""

    def _parse_mapping(self, node, source_code: bytes) -> Dict[str, Any]:
        result = {}
        for child in node.children:
            if child.type == "block_mapping_pair":
                key, val = self._parse_mapping_pair(child, source_code)
                if isinstance(key, str):
                    result[key] = val
        return result

    def _parse_flow_mapping(self, node, source_code: bytes) -> Dict[str, Any]:
        result = {}
        for child in node.children:
            if child.type == "flow_pair":
                key, val = self._parse_mapping_pair(child, source_code)
                if isinstance(key, str):
                    result[key] = val
        return result

    def _parse_mapping_pair(self, node, source_code: bytes) -> Tuple[str, Any]:
        # Key and value are separated by a ":" anonymous node; a missing value
        # (e.g. `key:`) yields None instead of dropping the key.
        significant = [c for c in node.children if c.type not in (":",)]
        if not significant:
            return "", None
        key = self._parse_node(significant[0], source_code)
        val = self._parse_node(significant[1], source_code) if len(significant) >= 2 else None
        return key, val

    def _get_node_text(self, node, source_code: bytes) -> str:
        return source_code[node.start_byte:node.end_byte].decode("utf-8")
